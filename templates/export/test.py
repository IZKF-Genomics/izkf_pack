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
        if self.path == "/export":
            response = {"job_id": "job-123"}
        elif self.path == "/export/job-123/refresh":
            response = {"job_id": "job-123"}
            self.server.refresh_payload = json.loads(  # type: ignore[attr-defined]
                self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            )
            body = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        else:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.payload = payload  # type: ignore[attr-defined]
        body = json.dumps(response).encode("utf-8")
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
                "main_report": "https://example.org/data/example_project_001/main_report.html",
                "username": "example_user",
                "password": "example_password",
                "publisher_results": [
                    {
                        "publisher": "sftp",
                        "url": "sftp://data.example.org",
                        "username": "example_user_example_project_001",
                        "password": "example_password",
                    },
                    {
                        "publisher": "apache",
                        "url": "https://example.org/data/example_project_001",
                        "username": "example_user",
                        "password": "example_password",
                    },
                    {
                        "publisher": "owncloud",
                        "url": "https://example.org/share/example_project_001",
                        "password": "example_password",
                    },
                ],
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
        prep_dir = project_dir / "scrna_prep"
        integrate_dir = project_dir / "scrna_integrate"
        annotate_dir = project_dir / "scrna_annotate"
        annotate_zebrafish_dir = project_dir / "scrna_annotate_zebrafish"
        ercc_dir = project_dir / "ercc"
        summary_dir = project_dir / "summary"
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
        (prep_dir / "results" / "tables").mkdir(parents=True)
        (prep_dir / "reports").mkdir(parents=True)
        (integrate_dir / "results" / "tables").mkdir(parents=True)
        (integrate_dir / "reports").mkdir(parents=True)
        (annotate_dir / "results" / "tables").mkdir(parents=True)
        (annotate_dir / "reports").mkdir(parents=True)
        (annotate_zebrafish_dir / "results" / "tables").mkdir(parents=True)
        (ercc_dir / "results").mkdir(parents=True)
        (summary_dir / "results").mkdir(parents=True)
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
        (prep_dir / "results" / "adata.prep.h5ad").write_text("h5ad\n", encoding="utf-8")
        (prep_dir / "results" / "run_info.yaml").write_text("template: scrna_prep\n", encoding="utf-8")
        (prep_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (prep_dir / "results" / "tables" / "qc_summary.csv").write_text("metric,value\n", encoding="utf-8")
        (prep_dir / "reports" / "scrna_prep.html").write_text("<html></html>\n", encoding="utf-8")
        (integrate_dir / "results" / "adata.integrated.h5ad").write_text("h5ad\n", encoding="utf-8")
        (integrate_dir / "results" / "run_info.yaml").write_text("template: scrna_integrate\n", encoding="utf-8")
        (integrate_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (integrate_dir / "results" / "tables" / "integration_metrics.csv").write_text("metric,value\n", encoding="utf-8")
        (integrate_dir / "reports" / "scrna_integrate.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_dir / "results" / "adata.annotated.h5ad").write_text("h5ad\n", encoding="utf-8")
        (annotate_dir / "results" / "run_info.yaml").write_text("template: scrna_annotate\n", encoding="utf-8")
        (annotate_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (annotate_dir / "results" / "tables" / "cluster_annotation_summary.csv").write_text("cluster,label\n", encoding="utf-8")
        (annotate_dir / "reports" / "00_annotation_overview.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_dir / "reports" / "01_celltypist.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_dir / "reports" / "02_scanvi.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_dir / "reports" / "03_decoupler_review.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_dir / "reports" / "04_scdeepsort.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_dir / "reports" / "05_scgpt.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "annotation_result.json").write_text('{"template": "scrna_annotate_zebrafish"}\n', encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "report.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "report.qmd").write_text("---\ntitle: test\n---\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "scrna_annotate_zebrafish_results.xlsx").write_text("xlsx\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "tables" / "cluster_annotation_summary.csv").write_text("cluster,label\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "tables" / "catalog_matches.csv").write_text("cluster,label\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "tables" / "differential_markers.csv").write_text("cluster,gene\n", encoding="utf-8")
        (ercc_dir / "results" / "ERCC.html").write_text("<html></html>\n", encoding="utf-8")
        (ercc_dir / "results" / "run_info.yaml").write_text("template: ercc\n", encoding="utf-8")
        (ercc_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (summary_dir / "results" / "summary_long.md").write_text("# Long analysis summary\n", encoding="utf-8")
        (summary_dir / "results" / "summary_short.md").write_text("# Short analysis summary\n", encoding="utf-8")
        (summary_dir / "results" / "summary_references.md").write_text("# References\n", encoding="utf-8")
        (summary_dir / "results" / "summary_long.html").write_text("<html></html>\n", encoding="utf-8")
        (summary_dir / "results" / "summary_short.html").write_text("<html></html>\n", encoding="utf-8")
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
                    "id": "scrna_prep",
                    "path": str(prep_dir),
                    "outputs": {
                        "results_dir": str((prep_dir / "results").resolve()),
                        "scrna_prep_h5ad": str((prep_dir / "results" / "adata.prep.h5ad").resolve()),
                    },
                },
                {
                    "id": "scrna_integrate",
                    "path": str(integrate_dir),
                    "outputs": {
                        "results_dir": str((integrate_dir / "results").resolve()),
                        "integrated_h5ad": str((integrate_dir / "results" / "adata.integrated.h5ad").resolve()),
                    },
                },
                {
                    "id": "scrna_annotate",
                    "path": str(annotate_dir),
                    "outputs": {
                        "results_dir": str((annotate_dir / "results").resolve()),
                        "annotated_h5ad": str((annotate_dir / "results" / "adata.annotated.h5ad").resolve()),
                    },
                },
                {
                    "id": "scrna_annotate_zebrafish",
                    "path": str(annotate_zebrafish_dir),
                    "outputs": {
                        "results_dir": str((annotate_zebrafish_dir / "results").resolve()),
                        "annotation_result": str((annotate_zebrafish_dir / "results" / "annotation_result.json").resolve()),
                        "html_report": str((annotate_zebrafish_dir / "results" / "report.html").resolve()),
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
                {
                    "id": "summary",
                    "instance_id": "summary_001",
                    "path": "summary",
                    "history_path": ".linkar/runs/summary_001",
                    "outputs": {
                        "results_dir": str((project_dir / ".linkar" / "runs" / "summary_001" / "results").resolve()),
                    },
                },
                {
                    "id": "summary",
                    "instance_id": "summary_002",
                    "path": "summary",
                    "history_path": ".linkar/runs/summary_002",
                    "outputs": {
                        "results_dir": str((project_dir / ".linkar" / "runs" / "summary_002" / "results").resolve()),
                    },
                },
            ],
        }
        (project_dir / "project.yaml").write_text(yaml.safe_dump(project_yaml, sort_keys=False), encoding="utf-8")

        prepare_only = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--prepare-only",
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
        assert "Prepare Only Complete" in prepare_only.stdout
        assert "Project templates:" in prepare_only.stdout
        assert "demultiplex (1), nfcore_3mrnaseq (2), dgea (2), methylation_array_analysis (1), scrna_prep (1), scrna_integrate (1), scrna_annotate (1), scrna_annotate_zebrafish (1), ercc (1), summary (2)" in prepare_only.stdout
        spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
        assert spec["project_name"] == "example_project_001"
        assert spec["authors"] == ["Example User, Example Org"]
        original_username = spec["username"]
        original_password = spec["password"]
        assert len(spec["export_list"]) == 17
        assert {entry["host"] for entry in spec["export_list"]} == {socket.gethostname()}
        export_srcs = {entry["src"] for entry in spec["export_list"]}
        export_dests = {entry["dest"] for entry in spec["export_list"]}
        assert str((ercc_dir / "results").resolve()) in export_srcs
        assert str((summary_dir / "results").resolve()) in export_srcs
        assert "2_Processed_data/nfcore_3mrnaseq/nfcore_liver" in export_dests
        assert "2_Processed_data/nfcore_3mrnaseq/nfcore_bile_duct" in export_dests
        assert "2_Processed_data/methylation_array_analysis/results" in export_dests
        assert "2_Processed_data/scrna_integrate/scrna_integrate/results" in export_dests
        assert "2_Processed_data/scrna_annotate/scrna_annotate/results" in export_dests
        assert "3_Reports/dgea/DGEA_Liver" in export_dests
        assert "3_Reports/dgea/DGEA_Bile_Duct" in export_dests
        assert "3_Reports/methylation_array_analysis" in export_dests
        assert "3_Reports/results/tables" in export_dests
        assert "3_Reports/scrna_prep" in export_dests
        assert "3_Reports/scrna_integrate/scrna_integrate" in export_dests
        assert "3_Reports/scrna_annotate/scrna_annotate" in export_dests
        assert "3_Reports/scrna_annotate_zebrafish/scrna_annotate_zebrafish/report.html" in export_dests
        assert "3_Reports/ercc/ercc" in export_dests
        assert "3_Reports/summary" in export_dests
        summary_entries = [entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/summary"]
        assert len(summary_entries) == 1
        assert summary_entries[0]["src"] == str((summary_dir / "results").resolve())
        dgea_report_entries = [entry for entry in spec["export_list"] if entry["dest"].startswith("3_Reports/dgea/")]
        assert any(
            any(link.get("path") == "DGEA_all_samples.html" for link in entry.get("report_links", []))
            for entry in dgea_report_entries
        )
        summary_paths = {link["path"] for link in summary_entries[0].get("report_links", [])}
        assert {"summary_long.html", "summary_short.html"} <= summary_paths
        methylation_report_entry = next(
            entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/methylation_array_analysis"
        )
        methylation_report_paths = {link["path"] for link in methylation_report_entry.get("report_links", [])}
        assert "." in methylation_report_paths
        assert "00_study_overview.html" in methylation_report_paths
        assert "02b_own_samples_embeddings.html" in methylation_report_paths
        assert "17_ProjectSpecific_Contrast.html" in methylation_report_paths
        methylation_support_entry = next(entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/results/tables")
        methylation_support_paths = {link["path"] for link in methylation_support_entry.get("report_links", [])}
        assert "." in methylation_support_paths
        prep_report_entries = [
            entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/scrna_prep"
        ]
        assert len(prep_report_entries) == 1
        prep_report_paths = {link["path"] for link in prep_report_entries[0].get("report_links", [])}
        assert "scrna_prep.html" in prep_report_paths
        integrate_entries = [
            entry for entry in spec["export_list"] if entry["dest"] == "2_Processed_data/scrna_integrate/scrna_integrate/results"
        ]
        assert len(integrate_entries) == 1
        integrate_paths = {link["path"] for link in integrate_entries[0].get("report_links", [])}
        assert "." in integrate_paths
        assert "adata.integrated.h5ad" in integrate_paths
        assert "tables" in integrate_paths
        integrate_report_entries = [
            entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/scrna_integrate/scrna_integrate"
        ]
        assert len(integrate_report_entries) == 1
        integrate_report_paths = {link["path"] for link in integrate_report_entries[0].get("report_links", [])}
        assert "scrna_integrate.html" in integrate_report_paths
        annotate_entries = [
            entry for entry in spec["export_list"] if entry["dest"] == "2_Processed_data/scrna_annotate/scrna_annotate/results"
        ]
        assert len(annotate_entries) == 1
        annotate_paths = {link["path"] for link in annotate_entries[0].get("report_links", [])}
        assert "." in annotate_paths
        assert "adata.annotated.h5ad" in annotate_paths
        assert "tables" in annotate_paths
        annotate_report_entries = [
            entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/scrna_annotate/scrna_annotate"
        ]
        assert len(annotate_report_entries) == 1
        annotate_report_paths = {link["path"] for link in annotate_report_entries[0].get("report_links", [])}
        assert "00_annotation_overview.html" in annotate_report_paths
        assert "01_celltypist.html" in annotate_report_paths
        assert "02_scanvi.html" in annotate_report_paths
        assert "03_decoupler_review.html" in annotate_report_paths
        assert "04_scdeepsort.html" in annotate_report_paths
        assert "05_scgpt.html" in annotate_report_paths
        annotate_zebrafish_report_entries = [
            entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/scrna_annotate_zebrafish/scrna_annotate_zebrafish/report.html"
        ]
        assert len(annotate_zebrafish_report_entries) == 1
        annotate_zebrafish_report_paths = {link["path"] for link in annotate_zebrafish_report_entries[0].get("report_links", [])}
        assert "." in annotate_zebrafish_report_paths
        assert (export_dir / "results" / "metadata_context.yaml").exists()
        assert (export_dir / "results" / "project_methods.md").exists()

        rebuilt = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--prepare-only",
                "true",
                "--reuse-credentials",
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
        assert "rebuilding existing" in rebuilt.stdout
        rebuilt_spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
        assert rebuilt_spec["username"] == original_username
        assert rebuilt_spec["password"] == original_password

        reset_build = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--prepare-only",
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
        assert "rebuilding existing" in reset_build.stdout
        reset_spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
        assert reset_spec["username"] == "project"
        assert reset_spec["password"] != original_password

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
                    "--reuse-spec",
                    "true",
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
            assert "Final Export Summary" in submit.stdout
            assert "Main Report" in submit.stdout
            assert "- URL: https://example.org/data/example_project_001/main_report.html" in submit.stdout
            assert "Access Credentials" in submit.stdout
            assert "- Username: example_user" in submit.stdout
            assert "- Password: example_password" in submit.stdout
            assert "Publisher Results" in submit.stdout
            assert "1. SFTP" in submit.stdout
            assert "- Username: example_user_example_project_001" in submit.stdout
            assert "2. APACHE" in submit.stdout
            assert "3. OWNCLOUD" in submit.stdout
            assert "JSON Patch for MS Planner" in submit.stdout
            assert "'Project ID': 'example_project_001'," in submit.stdout
            assert (export_dir / "results" / "export_job_id.txt").read_text(encoding="utf-8").strip() == "job-123"
            assert "'Report URL': 'https://example.org/data/example_project_001/main_report.html'," in (
                export_dir / "results" / "export_final_message.txt"
            ).read_text(encoding="utf-8")
            payload = json.loads((export_dir / "results" / "export_submission.json").read_text(encoding="utf-8"))
            assert payload["job_id"] == "job-123"
            state = json.loads((export_dir / "results" / "export_state.json").read_text(encoding="utf-8"))
            assert state["job_id"] == "job-123"
            assert state["username"] == "example_user"

            post_submit_reuse = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
                    "--prepare-only",
                    "true",
                    "--reuse-credentials",
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
            assert "rebuilding existing" in post_submit_reuse.stdout
            reused_spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
            assert reused_spec["username"] == "example_user"
            assert reused_spec["password"] == "example_password"

            refresh = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
                    "--refresh",
                    "true",
                    "--export-engine-api-url",
                    f"http://127.0.0.1:{server.server_port}",
                    "--project-dir",
                    str(project_dir),
                    "--template-dir",
                    str(TEMPLATE_DIR),
                    "--results-dir",
                    str(export_dir / "results"),
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
            assert "Refresh Export" in refresh.stdout
            refresh_payload = server.refresh_payload  # type: ignore[attr-defined]
            assert refresh_payload["project_name"] == "example_project_001"
            assert "export_list" in refresh_payload
            assert "username" not in refresh_payload
            assert "password" not in refresh_payload
            refresh_spec = json.loads((export_dir / "results" / "export_refresh_spec.json").read_text(encoding="utf-8"))
            assert refresh_spec == refresh_payload
        finally:
            server.shutdown()
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
