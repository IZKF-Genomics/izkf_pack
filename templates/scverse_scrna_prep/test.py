#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
import importlib.util

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
FUNCTIONS_DIR = TEMPLATE_DIR.parent.parent / "functions"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_function(name: str):
    return load_module(FUNCTIONS_DIR / f"{name}.py", f"test_{name}").resolve


def assert_fails(command: list[str], expected_message: str, *, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, text=True, capture_output=True, env=env)
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
    run_module = load_module(TEMPLATE_DIR / "run.py", "test_scverse_scrna_prep_run")
    with tempfile.TemporaryDirectory(prefix="linkar-scverse-scrna-prep-test-") as tmp:
        project_dir = Path(tmp) / "260417_scRNA_Project"
        results_dir = Path(tmp) / "results"
        (TEMPLATE_DIR / "config").mkdir(exist_ok=True)
        results_dir.mkdir()
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(yaml.safe_dump({}, sort_keys=False), encoding="utf-8")

        params = {
            "input_h5ad": "/tmp/input.h5ad",
            "input_matrix": "",
            "input_source_template": "",
            "ambient_correction_applied": "false",
            "ambient_correction_method": "none",
            "input_format": "h5ad",
            "var_names": "gene_symbols",
            "sample_metadata": "assets/samples.csv",
            "organism": "human",
            "batch_key": "batch",
            "condition_key": "condition",
            "sample_id_key": "sample_id",
            "doublet_method": "scrublet",
            "filter_predicted_doublets": "true",
            "qc_mode": "fixed",
            "qc_nmads": "3.0",
            "min_genes": "200",
            "min_cells": "3",
            "min_counts": "500",
            "max_pct_counts_mt": "20.0",
            "max_pct_counts_ribo": "",
            "max_pct_counts_hb": "",
            "n_top_hvgs": "3000",
            "n_pcs": "30",
            "n_neighbors": "15",
            "leiden_resolution": "",
            "resolution_grid": "0.2,0.4,0.6,0.8,1.0,1.2",
        }
        run_module.validate_params(params)
        run_module.write_project_config(
            TEMPLATE_DIR / "config" / "project.toml",
            params,
            project_name=project_dir.name,
            sample_metadata="assets/samples.csv",
        )
        original_project_dir = run_module.PROJECT_DIR
        original_results_dir = run_module.RESULTS_DIR
        run_module.PROJECT_DIR = project_dir
        run_module.RESULTS_DIR = results_dir
        try:
            run_module.write_run_info(
                results_dir / "run_info.yaml",
                params,
                project_name=project_dir.name,
                sample_metadata="assets/samples.csv",
            )
        finally:
            run_module.PROJECT_DIR = original_project_dir
            run_module.RESULTS_DIR = original_results_dir

        config_text = (TEMPLATE_DIR / "config" / "project.toml").read_text(encoding="utf-8")
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
                str(TEMPLATE_DIR / "run.py"),
            ],
            "Set either INPUT_H5AD or INPUT_MATRIX",
            env={**os.environ, "LINKAR_PACK_ROOT": str(TEMPLATE_DIR.parent.parent)},
        )
        assert_fails(
            [
                sys.executable,
                str(TEMPLATE_DIR / "run.py"),
            ],
            "Set ORGANISM",
            env={
                **os.environ,
                "LINKAR_PACK_ROOT": str(TEMPLATE_DIR.parent.parent),
                "INPUT_H5AD": "/tmp/input.h5ad",
            },
        )

    subprocess.run(
        [
            "bash",
            "-lc",
            """pixi run python - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, str(Path("lib").resolve()))
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
from scrna_prep_io import looks_like_gene_ids, normalize_text_series, resolve_qc_feature_names
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
normalized = normalize_text_series(pd.Series([None, np.nan, "", " nan ", "treated"]), fallback="unknown")
assert normalized.tolist() == ["unknown", "unknown", "unknown", "unknown", "treated"]
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
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    qmd_text = (TEMPLATE_DIR / "qc.qmd").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "assets" / "software_versions_spec.yaml").read_text(encoding="utf-8")

    assert "id: scverse_scrna_prep" in template_text
    assert 'exec python3 "${script_dir}/run.py"' in run_sh_text
    assert "quarto" in run_py_text
    assert "assets/samples.csv" in run_py_text
    assert "lib" in qmd_text
    assert "--output-dir" in run_py_text
    assert 'title: "scRNA Preprocessing QC"' in qmd_text
    assert "config/project.toml" in readme_text
    assert "selected_matrix_h5ad" in readme_text
    assert "doublet_method" in spec_text
    assert 'mask_var="highly_variable"' in qmd_text
    assert "sc.pp.scale(filtered" not in qmd_text
    assert "resolve_qc_feature_names" in qmd_text
    assert 'astype(str).fillna("unknown")' not in qmd_text
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
