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
                "message": "\n".join(
                    [
                        "'Project ID': 'example_project_001',",
                        "'Report URL': 'https://example.org/data/example_project_001/main_report.html',",
                        "'Username': 'example_user',",
                        "'Password': 'example_password',",
                        "'Download URL': 'https://example.org/share/example_project_001',",
                        "'Download command': \"wget -r -nH -np --cut-dirs=2 -l 8 -P example_project_001 --user=example_user --password=example_password https://example.org/data/example_project_001\",",
                    ]
                ),
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
        rnaseq_dir = project_dir / "nfcore_liver"
        rnaseq_bile_dir = project_dir / "nfcore_bile_duct"
        dgea_liver_dir = project_dir / "DGEA_Liver"
        dgea_bile_dir = project_dir / "DGEA_Bile_Duct"
        methylation_dir = project_dir / "methylation_array_analysis"
        ercc_dir = project_dir / "ercc"
        (demux_dir / "results" / "output").mkdir(parents=True)
        (demux_dir / "results" / "multiqc").mkdir(parents=True)
        (rnaseq_dir / "results" / "multiqc").mkdir(parents=True)
        (rnaseq_bile_dir / "results" / "multiqc").mkdir(parents=True)
        (dgea_liver_dir / "results").mkdir(parents=True)
        (dgea_bile_dir / "results").mkdir(parents=True)
        (methylation_dir / "results" / "tables").mkdir(parents=True)
        (methylation_dir / "results" / "figures").mkdir(parents=True)
        (methylation_dir / "results" / "rds").mkdir(parents=True)
        (methylation_dir / "reports").mkdir(parents=True)
        (ercc_dir / "results").mkdir(parents=True)
        (demux_dir / "results" / "output" / "sample.fastq.gz").write_text("fq\n", encoding="utf-8")
        (demux_dir / "results" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (rnaseq_dir / "results" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (rnaseq_bile_dir / "results" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (rnaseq_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (rnaseq_bile_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (dgea_liver_dir / "results" / "DGEA_all_samples.html").write_text("<html></html>\n", encoding="utf-8")
        (dgea_liver_dir / "results" / "run_info.yaml").write_text("template: dgea\n", encoding="utf-8")
        (dgea_liver_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (dgea_bile_dir / "results" / "DGEA_all_samples.html").write_text("<html></html>\n", encoding="utf-8")
        (dgea_bile_dir / "results" / "run_info.yaml").write_text("template: dgea\n", encoding="utf-8")
        (dgea_bile_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (methylation_dir / "results" / "run_info.yaml").write_text(
            "template: methylation_array_analysis\n", encoding="utf-8"
        )
        (methylation_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (methylation_dir / "reports" / "00_study_overview.html").write_text("<html></html>\n", encoding="utf-8")
        (methylation_dir / "reports" / "02b_own_samples_embeddings.html").write_text("<html></html>\n", encoding="utf-8")
        (methylation_dir / "reports" / "17_ProjectSpecific_Contrast.html").write_text("<html></html>\n", encoding="utf-8")
        (ercc_dir / "results" / "ERCC.html").write_text("<html></html>\n", encoding="utf-8")
        (ercc_dir / "results" / "run_info.yaml").write_text("template: ercc\n", encoding="utf-8")
        (ercc_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
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
                {
                    "id": "nfcore_3mrnaseq",
                    "path": str(rnaseq_bile_dir),
                    "outputs": {
                        "multiqc_report": str((rnaseq_bile_dir / "results" / "multiqc" / "multiqc_report.html").resolve()),
                    },
                },
                {
                    "id": "dgea",
                    "path": str(dgea_liver_dir),
                    "params": {"name": "Liver"},
                    "outputs": {
                        "results_dir": str((dgea_liver_dir / "results").resolve()),
                    },
                },
                {
                    "id": "dgea",
                    "path": str(dgea_bile_dir),
                    "params": {"name": "Bile Duct"},
                    "outputs": {
                        "results_dir": str((dgea_bile_dir / "results").resolve()),
                    },
                },
                {
                    "id": "methylation_array_analysis",
                    "path": str(methylation_dir),
                    "outputs": {
                        "results_dir": str((methylation_dir / "results").resolve()),
                    },
                },
                {
                    "id": "ercc",
                    "path": str(ercc_dir),
                    "outputs": {
                        "results_dir": str((ercc_dir / "results").resolve()),
                        "html_report": str((ercc_dir / "results" / "ERCC.html").resolve()),
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
        assert "Project templates:" in dry_run.stdout
        assert "demultiplex (1), nfcore_3mrnaseq (2), dgea (2), methylation_array_analysis (1), ercc (1)" in dry_run.stdout
        spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
        assert spec["project_name"] == "example_project_001"
        assert spec["authors"] == ["Example User, Example Org"]
        assert len(spec["export_list"]) == 12
        assert {entry["host"] for entry in spec["export_list"]} == {socket.gethostname()}
        export_srcs = {entry["src"] for entry in spec["export_list"]}
        export_dests = {entry["dest"] for entry in spec["export_list"]}
        assert str((ercc_dir / "results").resolve()) in export_srcs
        assert "2_Processed_data/nfcore_3mrnaseq/nfcore_liver" in export_dests
        assert "2_Processed_data/nfcore_3mrnaseq/nfcore_bile_duct" in export_dests
        assert "2_Processed_data/dgea/DGEA_Liver/results" in export_dests
        assert "2_Processed_data/dgea/DGEA_Bile_Duct/results" in export_dests
        assert "2_Processed_data/methylation_array_analysis/results" in export_dests
        assert "3_Reports/dgea/DGEA_Liver" in export_dests
        assert "3_Reports/dgea/DGEA_Bile_Duct" in export_dests
        assert "3_Reports/methylation_array_analysis" in export_dests
        assert "3_Reports/ercc/ercc" in export_dests
        dgea_report_entries = [entry for entry in spec["export_list"] if entry["dest"].startswith("3_Reports/dgea/")]
        assert any(
            any(link.get("path") == "DGEA_all_samples.html" for link in entry.get("report_links", []))
            for entry in dgea_report_entries
        )
        methylation_report_entry = next(
            entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/methylation_array_analysis"
        )
        methylation_report_paths = {link["path"] for link in methylation_report_entry.get("report_links", [])}
        assert "." in methylation_report_paths
        assert "00_study_overview.html" in methylation_report_paths
        assert "02b_own_samples_embeddings.html" in methylation_report_paths
        assert "17_ProjectSpecific_Contrast.html" in methylation_report_paths
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
            assert "JSON Patch for MS Planner" in submit.stdout
            assert "'Project ID': 'example_project_001'," in submit.stdout
            assert (export_dir / "results" / "export_job_id.txt").read_text(encoding="utf-8").strip() == "job-123"
            assert "'Report URL': 'https://example.org/data/example_project_001/main_report.html'," in (
                export_dir / "results" / "export_final_message.txt"
            ).read_text(encoding="utf-8")
            payload = json.loads((export_dir / "results" / "export_submission.json").read_text(encoding="utf-8"))
            assert payload["job_id"] == "job-123"
        finally:
            server.shutdown()
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
