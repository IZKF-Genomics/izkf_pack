#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent


def read_docx_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read("word/document.xml").decode("utf-8")


class FakeLLMHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        FakeLLMHandler.requests.append(payload)
        prompt = payload["messages"][-1]["content"]
        content = {
            "methods_short": "Single-cell RNA-seq quality control and analysis were performed from the supplied Scanpy and CellTypist workflow evidence.",
            "methods_long": "The workflow evidence contained Scanpy preprocessing, cell filtering, normalization, PCA, Leiden clustering, and CellTypist annotation steps. FASTQ and BAM files were not parsed as text evidence.",
            "references": "Wolf et al. Scanpy. Genome Biology. 2018.\nDomínguez Conde et al. CellTypist-related immune annotation resource. Science. 2022.",
        }
        body = json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class FakeLLMServer:
    def __enter__(self) -> "FakeLLMServer":
        FakeLLMHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLMHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    @property
    def requests(self) -> list[dict[str, object]]:
        return FakeLLMHandler.requests


def test_llm_driven_docx_only() -> None:
    with tempfile.TemporaryDirectory() as tmpdir, FakeLLMServer() as llm:
        root = Path(tmpdir)
        inputs = root / "analysis"
        (inputs / ".pixi").mkdir(parents=True)
        (inputs / ".renv").mkdir()
        (inputs / "data").mkdir()
        (inputs / "workflow.yaml").write_text(
            yaml.safe_dump(
                {
                    "qc": {"min_genes": 200, "max_pct_mt": 20},
                    "annotation": {"method": "CellTypist", "model": "Immune_All_Low.pkl"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (inputs / "analysis.py").write_text(
            "\n".join(
                [
                    "import scanpy as sc",
                    "import celltypist",
                    "sc.pp.filter_cells(adata, min_genes=200)",
                    "sc.pp.normalize_total(adata)",
                    "sc.tl.pca(adata)",
                    "sc.tl.leiden(adata)",
                ]
            ),
            encoding="utf-8",
        )
        (inputs / ".pixi" / "pixi.toml").write_text("should not be read\n", encoding="utf-8")
        (inputs / ".renv" / "activate.R").write_text("should not be read\n", encoding="utf-8")
        (inputs / "data" / "reads.fastq.gz").write_bytes(b"not text")
        (inputs / "data" / "alignment.bam").write_bytes(b"BAM\1")

        results = root / "results"
        completed = subprocess.run(
            [
                sys.executable,
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results),
                "--input-paths",
                str(inputs),
                "--out-file",
                "Draft_Methods.docx",
                "--llm-base-url",
                llm.base_url,
                "--llm-model",
                "fake-model",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={"LINKAR_LLM_API_KEY": "test-key"},
        )

        assert "included text from 2 files" in completed.stdout
        assert (results / "methods.docx").exists()
        assert (results / "Draft_Methods.docx").exists()
        assert (results / "out_file.txt").read_text(encoding="utf-8").strip().endswith("Draft_Methods.docx")
        assert not (results / "methods_context.yaml").exists()
        xml = read_docx_xml(results / "methods.docx")
        assert "Short Version" in xml
        assert "Long Version" in xml
        assert "Scanpy" in xml
        assert "CellTypist" in xml

        prompt = llm.requests[0]["messages"][-1]["content"]
        assert "Return only valid JSON" in prompt
        assert "analysis.py" in prompt
        assert "workflow.yaml" in prompt
        assert "reads.fastq.gz" in prompt
        assert "included_text=false" in prompt
        assert "should not be read" not in prompt


def test_keep_intermediates_and_list_input() -> None:
    with tempfile.TemporaryDirectory() as tmpdir, FakeLLMServer() as llm:
        root = Path(tmpdir)
        script = root / "run.R"
        log = root / "multiqc.log"
        script.write_text("library(DESeq2)\ndds <- DESeq(dds)\n", encoding="utf-8")
        log.write_text("MultiQC v1.21 summarized FastQC and Salmon outputs\n", encoding="utf-8")
        results = root / "results"

        subprocess.run(
            [
                sys.executable,
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results),
                "--input-paths",
                json.dumps([str(script), str(log)]),
                "--keep-intermediates",
                "true",
                "--llm-base-url",
                llm.base_url,
                "--llm-model",
                "fake-model",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={"LINKAR_LLM_API_KEY": "test-key"},
        )

        context = yaml.safe_load((results / "methods_context.yaml").read_text(encoding="utf-8"))
        response = json.loads((results / "methods_response.json").read_text(encoding="utf-8"))
        prompt = (results / "methods_prompt.md").read_text(encoding="utf-8")
        assert context["files_total"] == 2
        assert context["files_with_text"] == 2
        assert response["used_llm"] is True
        assert "DESeq2" in prompt
        assert "MultiQC" in prompt


def test_llm_settings_from_environment() -> None:
    with tempfile.TemporaryDirectory() as tmpdir, FakeLLMServer() as llm:
        root = Path(tmpdir)
        script = root / "analysis.py"
        script.write_text("import scanpy as sc\nsc.pp.normalize_total(adata)\n", encoding="utf-8")
        results = root / "results"
        env = os.environ.copy()
        env.update(
            {
                "LINKAR_LLM_API_KEY": "test-key",
                "LINKAR_LLM_BASE_URL": llm.base_url,
                "LINKAR_LLM_MODEL": "fake-model-from-env",
            }
        )

        subprocess.run(
            [
                sys.executable,
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results),
                "--input-paths",
                str(script),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        assert (results / "methods.docx").exists()
        assert llm.requests[0]["model"] == "fake-model-from-env"


def test_template_contract_mentions_direct_llm_docx() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    assert "mode: direct" in template_text
    assert "out_file:" in template_text
    assert "methods_docx:" in template_text
    assert "LLM-driven" in readme_text or "LLM" in readme_text
    assert "results/methods.docx" in readme_text
    assert "keep_intermediates" in readme_text


def main() -> int:
    test_llm_driven_docx_only()
    test_keep_intermediates_and_list_input()
    test_llm_settings_from_environment()
    test_template_contract_mentions_direct_llm_docx()
    print("methods_from_paths template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
