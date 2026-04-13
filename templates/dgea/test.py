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
        (salmon_dir / "tx2gene.tsv").write_text("tx1\tgene1\tGene1\n", encoding="utf-8")
        samplesheet = workspace / "samplesheet.csv"
        samplesheet.write_text(
            "sample,group,id\nWT_1,WT,1\nKO_1,KO,1\n",
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(TEMPLATE_DIR / "build_dgea_inputs.py"),
                "--workspace-dir",
                str(workspace),
                "--results-dir",
                str(results_dir),
                "--salmon-dir",
                str(salmon_dir),
                "--samplesheet",
                str(samplesheet),
                "--organism",
                "hsapiens",
                "--spikein",
                "None",
                "--application",
                "nfcore_3mrnaseq",
                "--name",
                "Study",
                "--authors",
                "A, B",
            ],
            check=True,
        )

        inputs_text = (workspace / "dgea_inputs.R").read_text(encoding="utf-8")
        assert "salmon_dir <- " in inputs_text
        assert str(salmon_dir.resolve()) in inputs_text
        assert 'organism <- "hsapiens"' in inputs_text

        run_info = yaml.safe_load((results_dir / "run_info.yaml").read_text(encoding="utf-8"))
        assert run_info["params"]["application"] == "nfcore_3mrnaseq"
        assert run_info["params"]["authors"] == "A, B"

        constructor = (TEMPLATE_DIR / "DGEA_constructor.R").read_text(encoding="utf-8")
        assert 'source("dgea_inputs.R")' in constructor
        assert "comparisons <- list()" in constructor

        settings = (TEMPLATE_DIR / ".vscode" / "settings.json").read_text(encoding="utf-8")
        assert "${workspaceFolder}/.pixi/envs/default/bin/R" in settings
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
