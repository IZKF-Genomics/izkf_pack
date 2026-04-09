#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent


class ExportHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/export":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.payload = payload  # type: ignore[attr-defined]
        body = json.dumps({"job_id": "job-123"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/export/final_message/job-123":
            self.send_error(404)
            return
        attempts = getattr(self.server, "final_message_attempts", 0) + 1  # type: ignore[attr-defined]
        self.server.final_message_attempts = attempts  # type: ignore[attr-defined]
        if attempts < 2:
            self.send_error(404)
            return
        body = json.dumps(
            {
                "message": "**Export complete**\n- path ready",
                "final_path": "/exports/example_project",
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        project_dir = root / "study"
        export_dir = project_dir / "export"
        demux_dir = project_dir / "demultiplex"
        rnaseq_dir = project_dir / "nfcore_3mrnaseq"
        (demux_dir / "results" / "output").mkdir(parents=True)
        (demux_dir / "results" / "multiqc").mkdir(parents=True)
        (rnaseq_dir / "results" / "multiqc").mkdir(parents=True)
        (demux_dir / "results" / "output" / "sample.fastq.gz").write_text("fq\n", encoding="utf-8")
        (demux_dir / "results" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (rnaseq_dir / "results" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (rnaseq_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        export_dir.mkdir(parents=True)

        project_yaml = {
            "id": "example_project_001",
            "author": {"name": "Example User", "organization": "Example Org"},
            "templates": [
                {
                    "id": "demultiplex",
                    "path": str(demux_dir),
                    "outputs": {
                        "output_dir": str((demux_dir / "results" / "output").resolve()),
                        "multiqc_report": str((demux_dir / "results" / "multiqc" / "multiqc_report.html").resolve()),
                    },
                    "params": {"agendo_id": "1001", "flowcell_id": "EXAMPLEFC"},
                },
                {
                    "id": "nfcore_3mrnaseq",
                    "path": str(rnaseq_dir),
                    "outputs": {
                        "multiqc_report": str((rnaseq_dir / "results" / "multiqc" / "multiqc_report.html").resolve()),
                    },
                },
            ],
        }
        (project_dir / "project.yaml").write_text(yaml.safe_dump(project_yaml, sort_keys=False), encoding="utf-8")

        dry_run = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--dry-run",
                "true",
                "--export-engine-api-url",
                "http://127.0.0.1:9",
                "--project-dir",
                str(project_dir),
                "--template-dir",
                str(TEMPLATE_DIR),
                "--results-dir",
                str(export_dir / "results"),
                "--metadata-source",
                "mock",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Dry Run Complete" in dry_run.stdout
        spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
        assert spec["project_name"] == "example_project_001"
        assert spec["authors"] == ["Example User, Example Org"]
        assert len(spec["export_list"]) == 3
        assert {entry["host"] for entry in spec["export_list"]} == {socket.gethostname()}
        assert (export_dir / "results" / "metadata_context.yaml").exists()
        assert (export_dir / "results" / "project_methods.md").exists()

        server = HTTPServer(("127.0.0.1", 0), ExportHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            submit = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
                    "--results-dir",
                    str(export_dir / "results"),
                    "--project-dir",
                    str(project_dir),
                    "--template-dir",
                    str(TEMPLATE_DIR),
                    "--export-engine-api-url",
                    f"http://127.0.0.1:{server.server_port}",
                    "--metadata-source",
                    "mock",
                    "--poll-interval-seconds",
                    "1",
                    "--timeout-seconds",
                    "5",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert "Job ID:" in submit.stdout
            assert "path ready" in submit.stdout
            assert (export_dir / "results" / "export_job_id.txt").read_text(encoding="utf-8").strip() == "job-123"
            payload = json.loads((export_dir / "results" / "export_submission.json").read_text(encoding="utf-8"))
            assert payload["job_id"] == "job-123"
        finally:
            server.shutdown()
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
