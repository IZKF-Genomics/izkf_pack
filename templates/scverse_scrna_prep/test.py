#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="linkar-scverse-scrna-prep-test-") as tmp:
        workspace = Path(tmp) / "workspace"
        project_dir = Path(tmp) / "260417_scRNA_Project"
        results_dir = workspace / "results"
        workspace.mkdir()
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(
            yaml.safe_dump({"author": {"name": "A. Scientist"}}, sort_keys=False),
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(TEMPLATE_DIR / "build_scrna_prep_inputs.py"),
                "--workspace-dir",
                str(workspace),
                "--project-dir",
                str(project_dir),
                "--results-dir",
                str(results_dir),
                "--input-h5ad",
                "/tmp/input.h5ad",
                "--input-format",
                "h5ad",
                "--sample-metadata",
                "config/samples.csv",
                "--organism",
                "human",
                "--doublet-method",
                "scrublet",
                "--filter-predicted-doublets",
                "true",
            ],
            check=True,
        )

        config_text = (workspace / "config" / "project.toml").read_text(encoding="utf-8")
        run_info = yaml.safe_load((results_dir / "run_info.yaml").read_text(encoding="utf-8"))

        assert 'name = "260417_scRNA_Project"' in config_text
        assert 'authors = "A. Scientist"' in config_text
        assert 'input_h5ad = "/tmp/input.h5ad"' in config_text
        assert 'input_format = "h5ad"' in config_text
        assert 'doublet_method = "scrublet"' in config_text
        assert "filter_predicted_doublets = true" in config_text

        assert run_info["params"]["project_name"] == "260417_scRNA_Project"
        assert run_info["params"]["authors"] == "A. Scientist"
        assert run_info["params"]["organism"] == "human"
        assert run_info["params"]["filter_predicted_doublets"] is True

    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    qmd_text = (TEMPLATE_DIR / "00_qc.qmd").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")

    assert "id: scverse_scrna_prep" in template_text
    assert "build_scrna_prep_inputs.py" in run_sh_text
    assert "--output-dir reports" in run_sh_text
    assert 'title: "00 scRNA Preprocessing QC"' in qmd_text
    assert "config/project.toml" in readme_text
    assert "doublet_method" in spec_text
    print("scverse_scrna_prep template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
