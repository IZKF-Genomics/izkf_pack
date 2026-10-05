#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

from export_common import generate_summary_markdown, template_placeholders


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
            self.server.refresh_requested = True  # type: ignore[attr-defined]
            self.server.refresh_detail_reads = 0  # type: ignore[attr-defined]
            self.server.refresh_ready = False  # type: ignore[attr-defined]
            refresh_count = getattr(self.server, "refresh_count", 0) + 1  # type: ignore[attr-defined]
            self.server.refresh_count = refresh_count  # type: ignore[attr-defined]
            self.server.next_record_updated_at = f"2026-01-{refresh_count + 1:02d}T00:00:00Z"  # type: ignore[attr-defined]
            self.server.refresh_should_fail = getattr(self.server, "fail_next_refresh", False)  # type: ignore[attr-defined]
            self.server.fail_next_refresh = False  # type: ignore[attr-defined]
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
        if self.path == "/export/job-123":
            refresh_requested = getattr(self.server, "refresh_requested", False)  # type: ignore[attr-defined]
            if refresh_requested:
                reads = getattr(self.server, "refresh_detail_reads", 0) + 1  # type: ignore[attr-defined]
                self.server.refresh_detail_reads = reads  # type: ignore[attr-defined]
                if reads >= 2:
                    self.server.refresh_ready = True  # type: ignore[attr-defined]
                    self.server.record_updated_at = self.server.next_record_updated_at  # type: ignore[attr-defined]
            updated_at = getattr(self.server, "record_updated_at", "2026-01-01T00:00:00Z")  # type: ignore[attr-defined]
            refresh_ready = getattr(self.server, "refresh_ready", False)  # type: ignore[attr-defined]
            refresh_should_fail = getattr(self.server, "refresh_should_fail", False)  # type: ignore[attr-defined]
            status = "failed" if refresh_ready and refresh_should_fail else "completed"
            detail = {
                "job_id": "job-123",
                "updated_at": updated_at,
                "status": status,
                "record_status": "failed" if status == "failed" else "active",
                "error": "simulated refresh failure" if status == "failed" else None,
            }
            body = json.dumps(detail).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/export/job-123/poll":
            attempts = getattr(self.server, "poll_attempts", 0) + 1  # type: ignore[attr-defined]
            self.server.poll_attempts = attempts  # type: ignore[attr-defined]
            refresh_ready = getattr(self.server, "refresh_ready", False)  # type: ignore[attr-defined]
            refresh_should_fail = getattr(self.server, "refresh_should_fail", False)  # type: ignore[attr-defined]
            # Deliberately keep returning a stale successful result after a
            # failed refresh. The client must trust the new detail generation,
            # not this previous /poll terminal state.
            status = "completed" if attempts >= 2 else "running"
            message = "Export completed"
            body = json.dumps({"job_id": "job-123", "status": status, "message": message}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path != "/export/final_message/job-123":
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
    assert template_placeholders("nfcore_rnaseq", {"path": "nfcore_rnaseq"})["template_basename_suffix"] == ""
    assert template_placeholders("dgea", {"path": "dgea"})["template_basename_suffix"] == ""
    assert template_placeholders("dgea", {"path": "DGEA_Liver"})["template_basename_suffix"] == "/DGEA_Liver"
    assert template_placeholders("mirna_differential", {"path": "mirna_differential"})["template_basename_suffix"] == ""
    assert template_placeholders("mirna_differential", {"path": "miRNA_Pig_OIM"})["template_basename_suffix"] == "/miRNA_Pig_OIM"
    assert template_placeholders("cellranger_multi", {"path": "cellranger_multi"})["template_basename_suffix"] == ""
    assert template_placeholders("cellranger_multi", {"path": "cellranger_multi_repeat"})["template_basename_suffix"] == "/cellranger_multi_repeat"

    with tempfile.TemporaryDirectory() as summary_tmpdir:
        summary_project = Path(summary_tmpdir)
        (summary_project / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "summary_fallback_test",
                    "templates": [
                        {"id": "demultiplex", "template_version": "0.2.2", "state": "rendered"},
                        {"id": "nfcore_3mrnaseq", "state": "completed"},
                        {"id": "export", "state": "rendered"},
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        markdown, templates_count, citation_count = generate_summary_markdown(summary_project, "full")
        assert "demultiplex" in markdown and "nfcore_3mrnaseq" in markdown
        assert "bpm" not in markdown.lower() and "Automatic generation failed" not in markdown
        assert templates_count == 2
        assert citation_count == 0

        summary_results = summary_project / "summary" / "results"
        summary_results.mkdir(parents=True)
        (summary_results / "summary_long.md").write_text("# Existing long summary\n", encoding="utf-8")
        (summary_results / "summary_short.md").write_text("# Existing short summary\n", encoding="utf-8")
        (summary_results / "summary_context.yaml").write_text(
            yaml.safe_dump({"runs": [{"template": "a"}, {"template": "b"}], "citation_ids": ["x", "y"]}),
            encoding="utf-8",
        )
        markdown, templates_count, citation_count = generate_summary_markdown(summary_project, "concise")
        assert markdown == "# Existing short summary\n"
        assert templates_count == 2
        assert citation_count == 2

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        project_dir = root / "study"
        export_dir = project_dir / "export"
        demux_dir = project_dir / "demultiplex"
        nfcore_demux_dir = project_dir / "nfcore_demultiplex"
        rnaseq_dir = project_dir / "nfcore_liver"
        rnaseq_bile_dir = project_dir / "nfcore_bile_duct"
        cellranger_multi_dir = project_dir / "cellranger_multi"
        dgea_liver_dir = project_dir / "DGEA_Liver"
        dgea_bile_dir = project_dir / "DGEA_Bile_Duct"
        methylation_dir = project_dir / "methylation_array_analysis"
        prep_dir = project_dir / "scrna_prep"
        integrate_dir = project_dir / "scrna_integrate"
        annotate_dir = project_dir / "scrna_annotate"
        annotate_celltypist_dir = project_dir / "scrna_annotate_celltypist"
        annotate_manual_markers_dir = project_dir / "scrna_annotate_manual_markers"
        annotate_sctype_dir = project_dir / "scrna_annotate_sctype"
        annotate_audit_dir = project_dir / "scrna_annotate_audit"
        annotate_zebrafish_dir = project_dir / "scrna_annotate_zebrafish"
        ercc_dir = project_dir / "ercc"
        mirna_dir = project_dir / "mirna_differential"
        summary_dir = project_dir / "summary"
        (demux_dir / "results" / "output").mkdir(parents=True)
        (demux_dir / "results" / "multiqc").mkdir(parents=True)
        (nfcore_demux_dir / "output").mkdir(parents=True)
        (nfcore_demux_dir / "output" / "qc" / "multiqc").mkdir(parents=True)
        (nfcore_demux_dir / "multiqc").mkdir(parents=True)
        (rnaseq_dir / "results" / "multiqc").mkdir(parents=True)
        (rnaseq_bile_dir / "results" / "multiqc").mkdir(parents=True)
        (cellranger_multi_dir / "config").mkdir(parents=True)
        (cellranger_multi_dir / "generated" / "multi").mkdir(parents=True)
        (cellranger_multi_dir / "results" / "condition_a" / "outs" / "multiplexing_analysis").mkdir(parents=True)
        (cellranger_multi_dir / "results" / "condition_a" / "outs" / "per_sample_outs" / "condition_a_rep1").mkdir(parents=True)
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
        (annotate_celltypist_dir / "results" / "tables").mkdir(parents=True)
        (annotate_manual_markers_dir / "results" / "tables").mkdir(parents=True)
        (annotate_sctype_dir / "results" / "tables").mkdir(parents=True)
        (annotate_audit_dir / "results" / "tables").mkdir(parents=True)
        (annotate_zebrafish_dir / "results" / "tables").mkdir(parents=True)
        (ercc_dir / "results").mkdir(parents=True)
        (mirna_dir / "results" / "tables").mkdir(parents=True)
        (mirna_dir / "results" / "figures").mkdir(parents=True)
        (mirna_dir / "results" / "hairpin").mkdir(parents=True)
        (mirna_dir / "config").mkdir(parents=True)
        (mirna_dir / "reports").mkdir(parents=True)
        (summary_dir / "results").mkdir(parents=True)
        (demux_dir / "results" / "output" / "sample.fastq.gz").write_text("fq\n", encoding="utf-8")
        (demux_dir / "results" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (nfcore_demux_dir / "output" / "sample_R1.fastq.gz").write_text("fq\n", encoding="utf-8")
        (nfcore_demux_dir / "output" / "sample_R2.fastq.gz").write_text("fq\n", encoding="utf-8")
        (nfcore_demux_dir / "output" / "qc" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (nfcore_demux_dir / "multiqc" / "run_multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (rnaseq_dir / "results" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (rnaseq_bile_dir / "results" / "multiqc" / "multiqc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (rnaseq_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (rnaseq_bile_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (cellranger_multi_dir / "config" / "samples.csv").write_text(
            "sample,gex_fastq_dir,gex_fastq_id,feature_fastq_dir,feature_fastq_id,feature_type\n",
            encoding="utf-8",
        )
        (cellranger_multi_dir / "config" / "sample_assignments.csv").write_text(
            "gem_well,sample_id,hashtag_ids\ncondition_a,condition_a_rep1,Hashtag1\n",
            encoding="utf-8",
        )
        (cellranger_multi_dir / "config" / "custom_feature_reference.csv").write_text(
            "id,name,read,pattern,sequence,feature_type\nHashtag1,Hashtag1,R2,5P(BC),ACGT,Antibody Capture\n",
            encoding="utf-8",
        )
        (cellranger_multi_dir / "config" / "cellranger_multi.toml").write_text(
            '[reference]\ntranscriptome = "/refs/GRCm39"\n',
            encoding="utf-8",
        )
        (cellranger_multi_dir / "generated" / "feature_reference.csv").write_text(
            "id,name,read,pattern,sequence,feature_type\nHashtag1,Hashtag1,R2,5P(BC),ACGT,Antibody Capture\n",
            encoding="utf-8",
        )
        (cellranger_multi_dir / "generated" / "multi" / "condition_a.csv").write_text(
            "[gene-expression]\nreference,/refs/GRCm39\n",
            encoding="utf-8",
        )
        (cellranger_multi_dir / "results" / "runtime_command.json").write_text(
            '{"template":"cellranger_multi","commands":[]}\n', encoding="utf-8"
        )
        (cellranger_multi_dir / "results" / "software_versions.json").write_text(
            '{"software":[{"name":"cellranger","version":"10.0.0"}]}\n', encoding="utf-8"
        )
        cellranger_qc_dir = cellranger_multi_dir / "results" / "qc"
        cellranger_qc_dir.mkdir(parents=True)
        (cellranger_qc_dir / "qc_overview.html").write_text("<html></html>\n", encoding="utf-8")
        (cellranger_qc_dir / "sample_qc_overview.csv").write_text("Sample ID,GEX: Cells\n", encoding="utf-8")
        (cellranger_qc_dir / "gem_well_library_qc.csv").write_text(
            "GEM well,Metric Name,Metric Value\n", encoding="utf-8"
        )
        (cellranger_qc_dir / "hashtag_assignment_overview.csv").write_text(
            "GEM well,Singlet assigned %\n", encoding="utf-8"
        )
        cellranger_outs = cellranger_multi_dir / "results" / "condition_a" / "outs"
        (cellranger_outs / "qc_report.html").write_text("<html></html>\n", encoding="utf-8")
        (cellranger_outs / "qc_library_metrics.csv").write_text("metric,value\n", encoding="utf-8")
        (cellranger_outs / "qc_sample_metrics.csv").write_text("metric,value\n", encoding="utf-8")
        (cellranger_outs / "filtered_feature_bc_matrix.h5").write_text("h5\n", encoding="utf-8")
        (cellranger_outs / "multiplexing_analysis" / "tag_calls_summary.csv").write_text(
            "tag,cells\n", encoding="utf-8"
        )
        cellranger_sample_outs = cellranger_outs / "per_sample_outs" / "condition_a_rep1"
        (cellranger_sample_outs / "web_summary.html").write_text("<html></html>\n", encoding="utf-8")
        (cellranger_sample_outs / "sample_filtered_feature_bc_matrix.h5").write_text("h5\n", encoding="utf-8")
        (cellranger_sample_outs / "sample_cloupe.cloupe").write_text("cloupe\n", encoding="utf-8")
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
        (prep_dir / "results" / "scrna_prep.html").write_text("<html></html>\n", encoding="utf-8")
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
        for template_id, template_dir in [
            ("scrna_annotate_celltypist", annotate_celltypist_dir),
            ("scrna_annotate_manual_markers", annotate_manual_markers_dir),
            ("scrna_annotate_sctype", annotate_sctype_dir),
            ("scrna_annotate_zebrafish", annotate_zebrafish_dir),
        ]:
            (template_dir / "results" / "annotation_result.json").write_text(
                json.dumps({"template": template_id}) + "\n",
                encoding="utf-8",
            )
            (template_dir / "results" / "adata.annotated.h5ad").write_text("h5ad\n", encoding="utf-8")
            (template_dir / "results" / "report.html").write_text("<html></html>\n", encoding="utf-8")
            (template_dir / "results" / "output.cloupe").write_text("cloupe\n", encoding="utf-8")
        (annotate_audit_dir / "results" / "annotation_audit.json").write_text('{"template": "scrna_annotate_audit"}\n', encoding="utf-8")
        (annotate_audit_dir / "results" / "annotation_audit_cards.json").write_text("[]\n", encoding="utf-8")
        (annotate_audit_dir / "results" / "adata.final_annotated.h5ad").write_text("h5ad\n", encoding="utf-8")
        (annotate_audit_dir / "results" / "adata.final_annotated.cloupe").write_text("cloupe\n", encoding="utf-8")
        (annotate_audit_dir / "results" / "report.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_audit_dir / "results" / "audit_report_static.html").write_text("<html></html>\n", encoding="utf-8")
        (annotate_audit_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (annotate_audit_dir / "results" / "tables" / "final_annotation_decisions_applied.csv").write_text(
            "cluster_id,final_label\n",
            encoding="utf-8",
        )
        (annotate_zebrafish_dir / "results" / "report.qmd").write_text("---\ntitle: test\n---\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "scrna_annotate_zebrafish_results.xlsx").write_text("xlsx\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "tables" / "cluster_annotation_summary.csv").write_text("cluster,label\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "tables" / "catalog_matches.csv").write_text("cluster,label\n", encoding="utf-8")
        (annotate_zebrafish_dir / "results" / "tables" / "differential_markers.csv").write_text("cluster,gene\n", encoding="utf-8")
        (ercc_dir / "results" / "ERCC.html").write_text("<html></html>\n", encoding="utf-8")
        (ercc_dir / "results" / "run_info.yaml").write_text("template: ercc\n", encoding="utf-8")
        (ercc_dir / "results" / "software_versions.json").write_text('{"software": []}\n', encoding="utf-8")
        (mirna_dir / "results" / "tables" / "miRNA_differential_results.xlsx").write_text("xlsx\n", encoding="utf-8")
        (mirna_dir / "results" / "figures" / "pca.png").write_text("png\n", encoding="utf-8")
        (mirna_dir / "results" / "hairpin" / "status.txt").write_text("enabled\n", encoding="utf-8")
        (mirna_dir / "results" / "run_info.yaml").write_text("template: mirna_differential\n", encoding="utf-8")
        (mirna_dir / "config" / "analysis.yaml").write_text("contrasts: []\n", encoding="utf-8")
        (mirna_dir / "config" / "samples.csv").write_text("sample,include\n", encoding="utf-8")
        (mirna_dir / "reports" / "miRNA_differential_report.html").write_text("<html></html>\n", encoding="utf-8")
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
                    "id": "nfcore_demultiplex",
                    "path": str(nfcore_demux_dir / "output"),
                    "outputs": {
                        "output_dir": str((nfcore_demux_dir / "output").resolve()),
                        "multiqc_report": str(
                            (nfcore_demux_dir / "output" / "qc" / "multiqc" / "multiqc_report.html").resolve()
                        ),
                        "run_multiqc_report": str((nfcore_demux_dir / "multiqc" / "run_multiqc_report.html").resolve()),
                    },
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
                    "id": "cellranger_multi",
                    "path": str(cellranger_multi_dir),
                    "outputs": {
                        "results_dir": str((cellranger_multi_dir / "results").resolve()),
                        "sample_manifest": str((cellranger_multi_dir / "config" / "samples.csv").resolve()),
                        "sample_assignments": str(
                            (cellranger_multi_dir / "config" / "sample_assignments.csv").resolve()
                        ),
                        "generated_feature_reference": str(
                            (cellranger_multi_dir / "generated" / "feature_reference.csv").resolve()
                        ),
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
                    "id": "scrna_annotate_celltypist",
                    "path": str(annotate_celltypist_dir),
                    "outputs": {
                        "results_dir": str((annotate_celltypist_dir / "results").resolve()),
                        "annotation_result": str((annotate_celltypist_dir / "results" / "annotation_result.json").resolve()),
                        "annotated_h5ad": str((annotate_celltypist_dir / "results" / "adata.annotated.h5ad").resolve()),
                        "html_report": str((annotate_celltypist_dir / "results" / "report.html").resolve()),
                    },
                },
                {
                    "id": "scrna_annotate_manual_markers",
                    "path": str(annotate_manual_markers_dir),
                    "outputs": {
                        "results_dir": str((annotate_manual_markers_dir / "results").resolve()),
                        "annotation_result": str((annotate_manual_markers_dir / "results" / "annotation_result.json").resolve()),
                        "annotated_h5ad": str((annotate_manual_markers_dir / "results" / "adata.annotated.h5ad").resolve()),
                        "html_report": str((annotate_manual_markers_dir / "results" / "report.html").resolve()),
                    },
                },
                {
                    "id": "scrna_annotate_sctype",
                    "path": str(annotate_sctype_dir),
                    "outputs": {
                        "results_dir": str((annotate_sctype_dir / "results").resolve()),
                        "annotation_result": str((annotate_sctype_dir / "results" / "annotation_result.json").resolve()),
                        "annotated_h5ad": str((annotate_sctype_dir / "results" / "adata.annotated.h5ad").resolve()),
                        "html_report": str((annotate_sctype_dir / "results" / "report.html").resolve()),
                    },
                },
                {
                    "id": "scrna_annotate_audit",
                    "path": str(annotate_audit_dir),
                    "outputs": {
                        "results_dir": str((annotate_audit_dir / "results").resolve()),
                        "annotation_audit": str((annotate_audit_dir / "results" / "annotation_audit.json").resolve()),
                        "final_h5ad": str((annotate_audit_dir / "results" / "adata.final_annotated.h5ad").resolve()),
                        "final_cloupe": str((annotate_audit_dir / "results" / "adata.final_annotated.cloupe").resolve()),
                        "static_html_report": str((annotate_audit_dir / "results" / "audit_report_static.html").resolve()),
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
                    "id": "mirna_differential",
                    "path": str(mirna_dir),
                    "params": {"name": "Pig OIM", "organism": "sscrofa"},
                    "outputs": {
                        "results_dir": str((mirna_dir / "results").resolve()),
                        "report_html": str((mirna_dir / "reports" / "miRNA_differential_report.html").resolve()),
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

        prepare_result = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--prepare",
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
        assert "Prepare Complete" in prepare_result.stdout
        assert "Project templates:" in prepare_result.stdout
        assert "demultiplex (1), nfcore_demultiplex (1), nfcore_3mrnaseq (2), cellranger_multi (1), dgea (2), methylation_array_analysis (1), scrna_prep (1), scrna_integrate (1), scrna_annotate (1), scrna_annotate_celltypist (1), scrna_annotate_manual_markers (1), scrna_annotate_sctype (1), scrna_annotate_audit (1), scrna_annotate_zebrafish (1), ercc (1), mirna_differential (1), summary (2)" in prepare_result.stdout
        spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
        assert spec["project_name"] == "example_project_001"
        assert spec["authors"] == ["Example User, Example Org"]
        assert "username" not in spec
        assert "password" not in spec
        credentials_path = export_dir / "results" / "export_credentials.json"
        credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
        original_username = credentials["username"]
        original_password = credentials["password"]
        assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600
        assert len(spec["export_list"]) == 41
        assert {entry["host"] for entry in spec["export_list"]} == {socket.gethostname()}
        export_srcs = {entry["src"] for entry in spec["export_list"]}
        export_dests = {entry["dest"] for entry in spec["export_list"]}
        assert str((ercc_dir / "results").resolve()) in export_srcs
        assert str((summary_dir / "results").resolve()) in export_srcs
        assert str((nfcore_demux_dir / "output").resolve()) in export_srcs
        assert "1_Raw_data/nfcore_demultiplex/FASTQ" in export_dests
        assert "1_Raw_data/nfcore_demultiplex/demultiplexing_multiqc_report.html" in export_dests
        assert "1_Raw_data/nfcore_demultiplex/run_multiqc_report.html" in export_dests
        assert "2_Processed_data/nfcore_3mrnaseq/nfcore_liver" in export_dests
        assert "2_Processed_data/nfcore_3mrnaseq/nfcore_bile_duct" in export_dests
        assert "2_Processed_data/cellranger_multi/results" in export_dests
        assert "2_Processed_data/cellranger_multi/config" in export_dests
        assert "2_Processed_data/cellranger_multi/generated" in export_dests
        assert "2_Processed_data/methylation_array_analysis/results" in export_dests
        assert "2_Processed_data/scrna_integrate/scrna_integrate/results" in export_dests
        assert "2_Processed_data/scrna_annotate/scrna_annotate/results" in export_dests
        for template_id in [
            "scrna_annotate_celltypist",
            "scrna_annotate_manual_markers",
            "scrna_annotate_sctype",
            "scrna_annotate_zebrafish",
        ]:
            assert f"2_Processed_data/{template_id}/{template_id}/annotation_result.json" in export_dests
            assert f"2_Processed_data/{template_id}/{template_id}/adata.annotated.h5ad" in export_dests
            assert f"3_Reports/{template_id}/{template_id}/report.html" in export_dests
            if template_id != "scrna_annotate_manual_markers":
                assert f"3_Reports/{template_id}/{template_id}/output.cloupe" in export_dests
        assert "3_Reports/dgea/DGEA_Liver" in export_dests
        assert "3_Reports/dgea/DGEA_Bile_Duct" in export_dests
        assert "3_Reports/methylation_array_analysis" in export_dests
        assert "3_Reports/results/tables" in export_dests
        assert "3_Reports/scrna_prep" in export_dests
        assert "3_Reports/scrna_integrate/scrna_integrate" in export_dests
        assert "3_Reports/scrna_annotate/scrna_annotate" in export_dests
        assert "3_Reports/scrna_annotate_audit/scrna_annotate_audit" in export_dests
        assert "3_Reports/scrna_annotate_zebrafish/scrna_annotate_zebrafish/report.html" in export_dests
        assert "3_Reports/ercc/ercc" in export_dests
        assert "2_Processed_data/mirna_differential/results" in export_dests
        assert "2_Processed_data/mirna_differential/config" in export_dests
        assert "3_Reports/mirna_differential" in export_dests
        assert "3_Reports/summary" in export_dests
        cellranger_result_entry = next(
            entry for entry in spec["export_list"] if entry["dest"] == "2_Processed_data/cellranger_multi/results"
        )
        assert cellranger_result_entry["src"] == str((cellranger_multi_dir / "results").resolve())
        cellranger_result_paths = {link["path"] for link in cellranger_result_entry.get("report_links", [])}
        assert cellranger_result_paths == {
            ".",
            "qc/qc_overview.html",
            "condition_a/outs/qc_report.html",
            "condition_a/outs/per_sample_outs/condition_a_rep1/web_summary.html",
        }
        cellranger_result_names = {
            link["path"]: link["link_name"] for link in cellranger_result_entry.get("report_links", [])
        }
        assert cellranger_result_names["condition_a/outs/qc_report.html"] == "condition_a — GEM-well QC"
        assert (
            cellranger_result_names["qc/qc_overview.html"]
            == "Cell Ranger multi — cross-sample QC overview"
        )
        assert (
            cellranger_result_names["condition_a/outs/per_sample_outs/condition_a_rep1/web_summary.html"]
            == "condition_a_rep1 — Cell Ranger summary"
        )
        cellranger_config_entry = next(
            entry for entry in spec["export_list"] if entry["dest"] == "2_Processed_data/cellranger_multi/config"
        )
        assert {"."} == {
            link["path"] for link in cellranger_config_entry.get("report_links", [])
        }
        cellranger_generated_entry = next(
            entry for entry in spec["export_list"] if entry["dest"] == "2_Processed_data/cellranger_multi/generated"
        )
        assert {"feature_reference.csv"} == {
            link["path"] for link in cellranger_generated_entry.get("report_links", [])
        }
        mirna_results_entry = next(
            entry for entry in spec["export_list"] if entry["dest"] == "2_Processed_data/mirna_differential/results"
        )
        assert mirna_results_entry["src"] == str((mirna_dir / "results").resolve())
        mirna_result_paths = {link["path"] for link in mirna_results_entry.get("report_links", [])}
        assert {".", "tables", "figures", "hairpin"} <= mirna_result_paths
        mirna_report_entry = next(
            entry for entry in spec["export_list"] if entry["dest"] == "3_Reports/mirna_differential"
        )
        assert {link["path"] for link in mirna_report_entry.get("report_links", [])} == {
            "miRNA_differential_report.html"
        }
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
        for template_id in [
            "scrna_annotate_celltypist",
            "scrna_annotate_manual_markers",
            "scrna_annotate_sctype",
            "scrna_annotate_zebrafish",
        ]:
            annotation_result_entries = [
                entry
                for entry in spec["export_list"]
                if entry["dest"] == f"2_Processed_data/{template_id}/{template_id}/annotation_result.json"
            ]
            assert len(annotation_result_entries) == 1
            annotation_result_paths = {link["path"] for link in annotation_result_entries[0].get("report_links", [])}
            assert "." in annotation_result_paths
            report_entries = [
                entry
                for entry in spec["export_list"]
                if entry["dest"] == f"3_Reports/{template_id}/{template_id}/report.html"
            ]
            assert len(report_entries) == 1
            report_paths = {link["path"] for link in report_entries[0].get("report_links", [])}
            assert "." in report_paths
            cloupe_entries = [
                entry
                for entry in spec["export_list"]
                if entry["dest"] == f"3_Reports/{template_id}/{template_id}/output.cloupe"
            ]
            if template_id == "scrna_annotate_manual_markers":
                assert len(cloupe_entries) == 0
                continue
            assert len(cloupe_entries) == 1
            cloupe_paths = {link["path"] for link in cloupe_entries[0].get("report_links", [])}
            assert "." in cloupe_paths
        audit_entries = [
            entry
            for entry in spec["export_list"]
            if entry["dest"] == "3_Reports/scrna_annotate_audit/scrna_annotate_audit"
        ]
        assert len(audit_entries) == 1
        assert audit_entries[0]["src"] == str((annotate_audit_dir / "results").resolve())
        audit_paths = {link["path"] for link in audit_entries[0].get("report_links", [])}
        assert {"audit_report_static.html", "report.html", "adata.final_annotated.h5ad", "adata.final_annotated.cloupe", "tables"} <= audit_paths
        assert (export_dir / "results" / "metadata_context.yaml").exists()
        assert (export_dir / "results" / "project_summary.md").exists()

        preserved_spec_text = (export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8")
        reused = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--prepare",
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
        assert "using existing" in reused.stdout
        assert (export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8") == preserved_spec_text

        rebuilt = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--prepare",
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
            env={**os.environ, "LINKAR_REFRESH": "true"},
        )
        assert "rebuilding existing" in rebuilt.stdout
        rebuilt_spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
        assert "username" not in rebuilt_spec
        assert "password" not in rebuilt_spec
        rebuilt_credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
        assert rebuilt_credentials["username"] == original_username
        assert rebuilt_credentials["password"] == original_password
        assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600

        password_override = "operator_selected_password"
        override_build = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "build_export_bundle.py"),
                "--new",
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
            env={**os.environ, "LINKAR_EXPORT_PASSWORD": password_override},
        )
        assert password_override not in override_build.stdout
        override_credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
        assert override_credentials["password"] == password_override

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
            assert "Final Export Summary" in submit.stdout
            assert "Main Report" in submit.stdout
            assert "- URL: https://example.org/data/example_project_001/main_report.html" in submit.stdout
            assert "Access Credentials" in submit.stdout
            assert "- Username: example_user" in submit.stdout
            assert "- Password: example_password" in submit.stdout
            assert f"- Private file: {credentials_path}" in submit.stdout
            assert "example_password" in submit.stdout
            assert "Publisher Results" in submit.stdout
            assert "1. SFTP" in submit.stdout
            assert "- Username: example_user_example_project_001" in submit.stdout
            assert "2. APACHE" in submit.stdout
            assert "3. OWNCLOUD" in submit.stdout
            assert "JSON Patch for MS Planner" in submit.stdout
            assert "'Project ID': 'example_project_001'," in submit.stdout
            assert "'Password': 'example_password'," in submit.stdout
            assert "[REDACTED]" not in submit.stdout
            request_payload = server.payload  # type: ignore[attr-defined]
            assert request_payload["username"] == override_credentials["username"]
            assert request_payload["password"] == override_credentials["password"]
            assert (export_dir / "results" / "export_job_id.txt").read_text(encoding="utf-8").strip() == "job-123"
            final_message_text = (export_dir / "results" / "export_final_message.txt").read_text(encoding="utf-8")
            assert "'Report URL': 'https://example.org/data/example_project_001/main_report.html'," in final_message_text
            assert "example_password" not in final_message_text
            assert "[REDACTED]" in final_message_text
            payload = json.loads((export_dir / "results" / "export_submission.json").read_text(encoding="utf-8"))
            assert payload["job_id"] == "job-123"
            assert payload["poll"]["status"] == "completed"
            assert "example_password" not in json.dumps(payload)
            assert getattr(server, "poll_attempts", 0) >= 2
            state = json.loads((export_dir / "results" / "export_state.json").read_text(encoding="utf-8"))
            assert state["job_id"] == "job-123"
            assert state["username"] == "example_user"
            submitted_credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
            assert submitted_credentials["username"] == "example_user"
            assert submitted_credentials["password"] == "example_password"
            assert len(submitted_credentials["publishers"]) == 3
            assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600

            credentials_before_blocked_new = credentials_path.read_text(encoding="utf-8")
            blocked_new = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
                    "--results-dir",
                    str(export_dir / "results"),
                    "--project-dir",
                    str(project_dir),
                    "--template-dir",
                    str(TEMPLATE_DIR),
                    "--new",
                    "--export-engine-api-url",
                    f"http://127.0.0.1:{server.server_port}",
                    "--metadata-source",
                    "mock",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            assert blocked_new.returncode != 0
            assert "Cannot use --new" in blocked_new.stderr
            assert credentials_path.read_text(encoding="utf-8") == credentials_before_blocked_new

            hidden_password_submit = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
                    "--results-dir",
                    str(export_dir / "results"),
                    "--project-dir",
                    str(project_dir),
                    "--template-dir",
                    str(TEMPLATE_DIR),
                    "--hide-password",
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
            assert "- Password: example_password" not in hidden_password_submit.stdout
            assert "'Password': 'example_password'," not in hidden_password_submit.stdout
            assert "example_password" not in hidden_password_submit.stdout
            assert "[REDACTED]" in hidden_password_submit.stdout
            assert "example_password" not in (
                export_dir / "results" / "export_final_message.txt"
            ).read_text(encoding="utf-8")
            assert "example_password" not in (
                export_dir / "results" / "export_submission.json"
            ).read_text(encoding="utf-8")

            post_submit_reuse = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
                    "--prepare",
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
            assert "using existing" in post_submit_reuse.stdout
            reused_spec = json.loads((export_dir / "results" / "export_job_spec.json").read_text(encoding="utf-8"))
            assert "username" not in reused_spec
            assert "password" not in reused_spec
            reused_credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
            assert reused_credentials["username"] == "example_user"
            assert reused_credentials["password"] == "example_password"

            refresh = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
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
                env={**os.environ, "LINKAR_REFRESH": "true"},
            )
            assert "Update Export" in refresh.stdout
            assert "rebuilding existing" in refresh.stdout
            refresh_payload = server.refresh_payload  # type: ignore[attr-defined]
            assert refresh_payload["project_name"] == "example_project_001"
            assert "export_list" in refresh_payload
            assert "username" not in refresh_payload
            assert "password" not in refresh_payload
            refresh_spec = json.loads((export_dir / "results" / "export_refresh_spec.json").read_text(encoding="utf-8"))
            assert refresh_spec == refresh_payload
            assert getattr(server, "refresh_detail_reads", 0) >= 2

            prior_state = (export_dir / "results" / "export_state.json").read_text(encoding="utf-8")
            server.fail_next_refresh = True  # type: ignore[attr-defined]
            failed_refresh = subprocess.run(
                [
                    "python3",
                    str(TEMPLATE_DIR / "run.py"),
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
                check=False,
                capture_output=True,
                text=True,
            )
            assert failed_refresh.returncode != 0
            assert "Export Failed" in failed_refresh.stdout
            assert "simulated refresh failure" in failed_refresh.stdout
            assert "Final Export Summary" not in failed_refresh.stdout
            assert (export_dir / "results" / "export_state.json").read_text(encoding="utf-8") == prior_state

            template_config = yaml.safe_load((TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8"))
            assert template_config["params"]["prepare"]["type"] == "flag"
            assert template_config["params"]["new"]["type"] == "flag"
            assert template_config["params"]["hide_password"]["type"] == "flag"
            assert "run_args+=(--prepare)" in template_config["run"]["command"]
            assert "run_args+=(--new)" in template_config["run"]["command"]
            assert "run_args+=(--hide-password)" in template_config["run"]["command"]
            render_command = template_config["render"]["command"]
            assert "build_args+=(--new)" in render_command
            assert "refresh" not in template_config["params"]
            assert "export_password" not in template_config["params"]

            help_result = subprocess.run(
                ["python3", str(TEMPLATE_DIR / "run.py"), "--help"],
                check=True,
                capture_output=True,
                text=True,
            )
            assert "The first run creates an export" in help_result.stdout
            assert "later runs automatically update" in help_result.stdout
            assert "preserving its job ID, username, password, and publisher links" in help_result.stdout
            assert "linkar run export --refresh --prepare" in help_result.stdout
        finally:
            server.shutdown()
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
