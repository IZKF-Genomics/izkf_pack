#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        results_dir = workspace / "results"
        salmon_dir = workspace / "salmon"
        salmon_dir.mkdir()
        (salmon_dir / "salmon.merged.gene_tpm.tsv").write_text(
            "gene_id\tgene_name\tSampleA\tSampleB\n"
            "ERCC-00002_gene\tERCC-00002\t10\t12\n"
            "ERCC-00003_gene\tERCC-00003\t20\t18\n"
            "GENE1_gene\tGENE1\t100\t90\n",
            encoding="utf-8",
        )
        samplesheet = workspace / "samplesheet.csv"
        samplesheet.write_text("sample\nSampleA\nSampleB\n", encoding="utf-8")

        (workspace / "ERCC.qmd").write_text((TEMPLATE_DIR / "ERCC.qmd").read_text(encoding="utf-8"), encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                str(TEMPLATE_DIR / "build_ercc_inputs.py"),
                "--workspace-dir",
                str(workspace),
                "--results-dir",
                str(results_dir),
                "--salmon-dir",
                str(salmon_dir),
                "--samplesheet",
                str(samplesheet),
                "--authors",
                "A, B",
            ],
            check=True,
        )

        inputs_text = (workspace / "ercc_inputs.R").read_text(encoding="utf-8")
        runtime_qmd = (workspace / "ERCC.runtime.qmd").read_text(encoding="utf-8")
        run_info = yaml.safe_load((results_dir / "run_info.yaml").read_text(encoding="utf-8"))
        run_sh = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
        readme = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
        spec = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")

        assert "salmon_dir <- " in inputs_text
        assert str(salmon_dir.resolve()) in inputs_text
        assert str(samplesheet.resolve()) in inputs_text
        assert 'author: "A, B"' in runtime_qmd
        assert 'source("ercc_inputs.R")' in runtime_qmd
        assert "Missing required R packages" in runtime_qmd
        assert "Samplesheet sample names are missing" in runtime_qmd
        assert "{.panel-tabset}" in runtime_qmd
        assert 'cat("\\n\\n### ' in runtime_qmd
        assert run_info["params"]["sample_count"] == 2
        assert run_info["params"]["authors"] == "A, B"
        assert '--output "${results_dir}/software_versions.json"' in run_sh
        assert "default pack bindings" in readme
        assert "quarto" in spec
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
