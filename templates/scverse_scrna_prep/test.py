#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
import importlib.util

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
FUNCTIONS_DIR = TEMPLATE_DIR.parent.parent / "functions"


def load_function(name: str):
    path = FUNCTIONS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load function module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve


def assert_fails(command: list[str], expected_message: str) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert expected_message in combined


class FakeProject:
    def __init__(self, templates: list[dict]) -> None:
        self.data = {"templates": templates}


class FakeTemplate:
    root = TEMPLATE_DIR


class FakeContext:
    def __init__(self, templates: list[dict]) -> None:
        self.project = FakeProject(templates)
        self.template = FakeTemplate()
        self.resolved_params = {}

    def latest_output(self, key: str, template_id: str | None = None):
        for entry in reversed(self.project.data["templates"]):
            if template_id is not None and entry.get("id") != template_id:
                continue
            outputs = entry.get("outputs") or {}
            if key in outputs:
                return outputs[key]
        return None


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

sparse_counts = ad.AnnData(X=__import__("scipy").sparse.csr_matrix(np.random.poisson(1.0, size=(30, 12))))
import scanpy as sc
import pandas as pd
from scrna_prep_io import looks_like_gene_ids, resolve_qc_feature_names
sc.pp.normalize_total(sparse_counts, target_sum=1e4)
sc.pp.log1p(sparse_counts)
sc.pp.highly_variable_genes(sparse_counts, n_top_genes=5, flavor="seurat")
sc.tl.pca(sparse_counts, n_comps=4, svd_solver="arpack", mask_var="highly_variable")
assert __import__("scipy").sparse.issparse(sparse_counts.X)
assert sparse_counts.obsm["X_pca"].shape == (30, 4)

var = pd.DataFrame(
    {"gene_symbols": ["MT-CO1", "RPS18", "HBZ"]},
    index=["ENSG00000198888", "ENSG00000140988", "ENSG00000206172"],
)
resolved = resolve_qc_feature_names(var, var.index)
assert resolved.tolist() == ["MT-CO1", "RPS18", "HBZ"]
assert looks_like_gene_ids(pd.Index(var.index))
PY""",
        ],
        cwd=TEMPLATE_DIR,
        check=True,
    )

    upstream_templates = [
        {
            "id": "nfcore_scrnaseq",
            "params": {"genome": "GRCz11", "aligner": "star"},
            "outputs": {
                "selected_matrix_h5ad": "/tmp/results/star/mtx_conversions/combined_cellbender_filter_matrix.h5ad",
            },
        }
    ]
    ctx = FakeContext(upstream_templates)
    assert load_function("get_scrna_prep_input_h5ad")(ctx) == "/tmp/results/star/mtx_conversions/combined_cellbender_filter_matrix.h5ad"
    assert load_function("get_scrna_prep_input_source_template")(ctx) == "nfcore_scrnaseq"
    assert load_function("get_scrna_prep_ambient_correction_applied")(ctx) is True
    assert load_function("get_scrna_prep_ambient_correction_method")(ctx) == "cellbender"
    assert load_function("get_scrna_prep_organism")(ctx) == "drerio"

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
    assert "selected_matrix_h5ad" in readme_text
    assert "doublet_method" in spec_text
    assert 'mask_var="highly_variable"' in qmd_text
    assert "sc.pp.scale(filtered" not in qmd_text
    assert "resolve_qc_feature_names" in qmd_text
    assert "QC gene annotation still requires gene symbols" in template_text
    assert "authors:" not in template_text
    assert "--authors" not in run_sh_text
    assert "author:" not in qmd_text
    pack_text = (TEMPLATE_DIR.parent.parent / "linkar_pack.yaml").read_text(encoding="utf-8")
    pack_data = yaml.safe_load(pack_text)
    params = pack_data["templates"]["scverse_scrna_prep"]["params"]
    assert params["input_h5ad"]["function"] == "get_scrna_prep_input_h5ad"
    assert params["organism"]["function"] == "get_scrna_prep_organism"
    print("scverse_scrna_prep template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
