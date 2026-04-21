#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent


def assert_fails(command: list[str], expected_message: str) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert expected_message in combined


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="linkar-scverse-scrna-prep-test-") as tmp:
        workspace = Path(tmp) / "workspace"
        project_dir = Path(tmp) / "260417_scRNA_Project"
        results_dir = workspace / "results"
        workspace.mkdir()
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(yaml.safe_dump({}, sort_keys=False), encoding="utf-8")

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
        assert 'input_h5ad = "/tmp/input.h5ad"' in config_text
        assert 'input_format = "h5ad"' in config_text
        assert 'doublet_method = "scrublet"' in config_text
        assert "filter_predicted_doublets = true" in config_text
        assert "authors =" not in config_text

        assert run_info["params"]["project_name"] == "260417_scRNA_Project"
        assert run_info["params"]["organism"] == "human"
        assert run_info["params"]["filter_predicted_doublets"] is True
        assert "authors" not in run_info["params"]

        assert_fails(
            [
                sys.executable,
                str(TEMPLATE_DIR / "build_scrna_prep_inputs.py"),
                "--workspace-dir",
                str(workspace),
                "--project-dir",
                str(project_dir),
                "--results-dir",
                str(results_dir),
                "--organism",
                "human",
            ],
            "Set either --input-h5ad or --input-matrix",
        )
        assert_fails(
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
            ],
            "Set --organism",
        )

    subprocess.run(
        [
            "bash",
            "-lc",
            """pixi run python - <<'PY'
import numpy as np
import anndata as ad
from scrna_prep_io import ensure_preprocessing_counts_matrix, RAW_H5AD_ERROR

counts = ad.AnnData(X=np.array([[1, 0], [3, 4]], dtype=float))
counts = ensure_preprocessing_counts_matrix(counts, input_format="h5ad")
assert "counts" in counts.layers

normalized = ad.AnnData(X=np.array([[0.1, 1.2], [2.3, 3.4]], dtype=float))
try:
    ensure_preprocessing_counts_matrix(normalized, input_format="h5ad")
except RuntimeError as exc:
    assert RAW_H5AD_ERROR in str(exc)
else:
    raise AssertionError("expected raw-count validation failure")

layered = ad.AnnData(X=np.array([[0.1, 0.2], [0.3, 0.4]], dtype=float))
layered.layers["counts"] = np.array([[5, 0], [7, 9]], dtype=float)
layered = ensure_preprocessing_counts_matrix(layered, input_format="h5ad")
assert np.array_equal(np.asarray(layered.X), np.asarray(layered.layers["counts"]))
PY""",
        ],
        cwd=TEMPLATE_DIR,
        check=True,
    )

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
    assert "authors:" not in template_text
    assert "--authors" not in run_sh_text
    assert "author:" not in qmd_text
    print("scverse_scrna_prep template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
