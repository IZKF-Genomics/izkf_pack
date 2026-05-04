#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
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
        body = json.dumps(
            {
                "status": "completed",
                "main_report": "https://example.org/report",
                "project_name": "20250101_Test_Project_Assay_FASTQ",
                "username": "tester",
                "password": "secret-token",
                "publisher_results": [
                    {
                        "publisher": "apache",
                        "url": "https://example.org/data",
                        "username": "tester",
                        "password": "secret-token",
                    },
                    {
                        "publisher": "owncloud",
                        "url": "https://example.org/cloud",
                        "username": None,
                        "password": "secret-token",
                    },
                ],
                "final_path": "/exports/demux",
                "formatted_message": "**Export complete**",
                "message": (
                    "\n"
                    "'Project ID': '20250101_Test_Project_Assay_FASTQ',\n"
                    "'Report URL': 'https://example.org/report',\n"
                    "'Username': 'tester',\n"
                    "'Password': 'secret-token',\n"
                    "'Download URL': 'https://example.org/cloud',\n"
                    "'Download command': \"wget https://example.org/data\",\n"
                ),
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
        run_dir = root / "demux_run"
        results_dir = root / "results"
        (run_dir / ".linkar").mkdir(parents=True)
        actual_output_dir = run_dir / "results" / "output"
        project_output_dir = actual_output_dir / "Project_A"
        project_b_output_dir = actual_output_dir / "Project_B"
        actual_multiqc_report = run_dir / "results" / "multiqc" / "multiqc_report.html"
        project_multiqc_report = (
            project_output_dir / "qc" / "multiqc" / "multiqc_report.html"
        )
        actual_output_dir.mkdir(parents=True)
        actual_multiqc_report.parent.mkdir(parents=True)
        (actual_output_dir / "sample.fastq.gz").write_text("fq\n", encoding="utf-8")
        project_output_dir.mkdir(parents=True)
        (project_output_dir / "project_sample.fastq.gz").write_text("fq\n", encoding="utf-8")
        project_b_output_dir.mkdir(parents=True)
        (project_b_output_dir / "project_b_sample.fastq.gz").write_text("fq\n", encoding="utf-8")
        project_multiqc_report.parent.mkdir(parents=True)
        project_multiqc_report.write_text("<html>project</html>\n", encoding="utf-8")
        actual_multiqc_report.write_text("<html></html>\n", encoding="utf-8")
        (run_dir / "results" / "template_outputs.json").write_text(
            json.dumps(
                {
                    "outputs": {
                        "project_multiqc_reports": {
                            "Project_A": str(project_multiqc_report)
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        (run_dir / ".linkar" / "meta.json").write_text(
            json.dumps(
                {
                    "outputs": {
                        "demux_fastq_files": [str(actual_output_dir / "sample.fastq.gz")],
                        "output_dir": str(actual_output_dir),
                        "multiqc_report": str(actual_multiqc_report),
                    }
                }
            ),
            encoding="utf-8",
        )

        dry = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results_dir),
                "--run-dir",
                str(run_dir),
                "--author",
                "CKuo, IZKF",
                "--dry-run",
                "true",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Dry Run" in dry.stdout
        latest = run_dir / ".linkar" / "export_demux" / "latest"
        assert (latest / "export_job_spec.redacted.json").exists()
        dry_spec = json.loads((latest / "export_job_spec.json").read_text(encoding="utf-8"))
        assert dry_spec["project_name"] == "demux_run_demultiplex_demultiplex_demultiplex"
        assert dry_spec["authors"] == ["CKuo, IZKF"]
        assert dry_spec["export_list"][0]["project"] == dry_spec["project_name"]
        assert dry_spec["export_list"][0]["src"] == str(actual_output_dir.resolve())
        assert dry_spec["export_list"][0]["dest"] == "1_Raw_data/FASTQ"
        assert dry_spec["export_list"][1]["src"] == str(actual_multiqc_report.resolve())
        assert not (results_dir / "export_demux_summary.json").exists()

        project_dry = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results_dir),
                "--run-dir",
                str(run_dir),
                "--project-name",
                "Project_A_fastq_export",
                "--sample-project",
                "Project_A",
                "--dry-run",
                "true",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Dry Run" in project_dry.stdout
        project_spec = json.loads((latest / "export_job_spec.json").read_text(encoding="utf-8"))
        assert project_spec["project_name"] == "Project_A_fastq_export"
        assert project_spec["export_list"][0]["src"] == str(project_output_dir.resolve())
        assert project_spec["export_list"][0]["dest"] == "1_Raw_data/Project_A"
        assert project_spec["export_list"][1]["src"] == str(project_multiqc_report.resolve())

        (project_output_dir / ".linkar").mkdir()
        (project_output_dir / ".linkar" / "meta.json").write_text(
            json.dumps(
                {
                    "params": {"sample_project": "Project_A"},
                    "outputs": {
                        "demux_fastq_files": [str(project_output_dir / "project_sample.fastq.gz")],
                        "output_dir": str(project_output_dir),
                        "multiqc_report": str(project_multiqc_report),
                    },
                }
            ),
            encoding="utf-8",
        )
        (project_output_dir / "template_outputs.json").write_text(
            json.dumps(
                {
                    "outputs": {
                        "demux_fastq_files": [str(project_output_dir / "project_sample.fastq.gz")],
                        "output_dir": str(project_output_dir),
                        "multiqc_report": str(project_multiqc_report),
                    }
                }
            ),
            encoding="utf-8",
        )
        adopted_project_dry = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results_dir),
                "--run-dir",
                str(project_output_dir),
                "--project-name",
                "Project_A_adopted_fastq_export",
                "--dry-run",
                "true",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Dry Run" in adopted_project_dry.stdout
        adopted_latest = project_output_dir / ".linkar" / "export_demux" / "latest"
        adopted_project_spec = json.loads((adopted_latest / "export_job_spec.json").read_text(encoding="utf-8"))
        assert adopted_project_spec["project_name"] == "Project_A_adopted_fastq_export"
        assert adopted_project_spec["export_list"][0]["src"] == str(project_output_dir.resolve())
        assert adopted_project_spec["export_list"][0]["dest"] == "1_Raw_data/Project_A"
        assert adopted_project_spec["export_list"][1]["src"] == str(project_multiqc_report.resolve())

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            submit = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
                    "--results-dir",
                    str(results_dir),
                    "--run-dir",
                    str(run_dir),
                    "--export-engine-api-url",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert "job-123" in submit.stdout
            assert (latest / "export_response.json").exists()
            assert (latest / "export_final_message.json").exists()
            assert (latest / "export_job_id.txt").read_text(encoding="utf-8").strip() == "job-123"
            assert (latest / "export_final_path.txt").read_text(encoding="utf-8").strip() == "/exports/demux"
            assert (results_dir / "export_metadata_dir.txt").read_text(encoding="utf-8").strip() == str(latest)
            assert server.payload["export_list"][0]["project"] == server.payload["project_name"]
            assert "JSON Patch for MS Planner" in submit.stdout
            planner_block = submit.stdout.split("JSON Patch for MS Planner", 1)[1]
            assert '{\n  "Project ID"' not in planner_block
            assert '  "Project ID": "20250101_Test_Project_Assay_FASTQ",' in planner_block
            assert '  "Download command": "wget https://example.org/data",' in planner_block
            assert "Publisher Results" in submit.stdout
            assert "1. APACHE" in submit.stdout
        finally:
            server.shutdown()
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
