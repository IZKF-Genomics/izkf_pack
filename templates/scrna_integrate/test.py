#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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
    run_module = load_module(TEMPLATE_DIR / "run.py", "test_scrna_integrate_run")
    with tempfile.TemporaryDirectory(prefix="linkar-scverse-scrna-integrate-test-") as tmp:
        project_dir = Path(tmp) / "260421_scRNA_Integration"
        results_dir = Path(tmp) / "results"
        (TEMPLATE_DIR / "config").mkdir(exist_ok=True)
        results_dir.mkdir()
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(yaml.safe_dump({}, sort_keys=False), encoding="utf-8")

        params = {
            "input_h5ad": "/tmp/input.h5ad",
            "input_source_template": "scrna_prep",
            "integration_method": "scvi",
            "batch_key": "batch",
            "condition_key": "condition",
            "sample_id_key": "sample_id",
            "sample_label_key": "sample_display",
            "label_key_for_metrics": "cell_type",
            "run_scib_metrics": "true",
            "use_hvgs_only": "true",
            "n_top_hvgs": "3000",
            "n_pcs": "30",
            "n_neighbors": "15",
            "umap_min_dist": "0.5",
            "cluster_resolution": "0.8",
            "random_seed": "0",
            "harmony_theta": "2.0",
            "harmony_lambda": "1.0",
            "harmony_max_iter": "20",
            "bbknn_neighbors_within_batch": "3",
            "bbknn_trim": "0",
            "scanvi_label_key": "",
            "scanvi_unlabeled_category": "Unknown",
            "scvi_latent_dim": "30",
            "scvi_max_epochs": "200",
            "scvi_gene_likelihood": "zinb",
            "scvi_accelerator": "auto",
            "scvi_devices": "1",
        }
        run_module.validate_params(params)
        run_module.write_project_config(
            TEMPLATE_DIR / "config" / "project.toml",
            params,
            project_name=project_dir.name,
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
            )
        finally:
            run_module.PROJECT_DIR = original_project_dir
            run_module.RESULTS_DIR = original_results_dir

        config_text = (TEMPLATE_DIR / "config" / "project.toml").read_text(encoding="utf-8")
        run_info = yaml.safe_load((results_dir / "run_info.yaml").read_text(encoding="utf-8"))

        assert 'integration_method = "scvi"' in config_text
        assert 'batch_key = "batch"' in config_text
        assert 'label_key_for_metrics = "cell_type"' in config_text
        assert "run_scib_metrics = true" in config_text
        assert run_info["params"]["project_name"] == "260421_scRNA_Integration"
        assert run_info["params"]["integration_method"] == "scvi"
        assert run_info["params"]["run_scib_metrics"] is True

        assert_fails(
            [sys.executable, str(TEMPLATE_DIR / "run.py")],
            "Set INPUT_H5AD",
            env={**os.environ, "LINKAR_PACK_ROOT": str(TEMPLATE_DIR.parent.parent)},
        )
        assert_fails(
            [sys.executable, str(TEMPLATE_DIR / "run.py")],
            "Set SCANVI_LABEL_KEY",
            env={
                **os.environ,
                "LINKAR_PACK_ROOT": str(TEMPLATE_DIR.parent.parent),
                "INPUT_H5AD": "/tmp/input.h5ad",
                "BATCH_KEY": "batch",
                "INTEGRATION_METHOD": "scanvi",
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
import pandas as pd
import anndata as ad
from scipy import sparse

from integration_io import ensure_counts_layer, normalize_text_series, require_obs_column
from integration_methods import ensure_hvg_subset, run_baseline_embedding
from integration_metrics import compare_baseline_and_integrated

adata = ad.AnnData(X=sparse.csr_matrix(np.random.poisson(1.0, size=(20, 10))))
adata.layers["counts"] = adata.X.copy()
adata.obs["batch"] = ["a"] * 10 + ["b"] * 10
adata.obs["cell_type"] = ["t"] * 10 + ["b"] * 10
adata.var["highly_variable"] = [True] * 5 + [False] * 5

assert ensure_counts_layer(adata, method="scvi") == "counts"
normalized = normalize_text_series(pd.Series([None, np.nan, "", " nan ", "treated"]), fallback="unknown")
assert normalized.tolist() == ["unknown", "unknown", "unknown", "unknown", "treated"]
require_obs_column(adata, "batch", allow_single_category=False)

hvg = ensure_hvg_subset(adata, use_hvgs_only=True, n_top_hvgs=5)
assert hvg.n_vars == 5
baseline = run_baseline_embedding(hvg, n_pcs=4, n_neighbors=5, umap_min_dist=0.5, cluster_resolution=0.5, random_state=0)
metrics = compare_baseline_and_integrated(
    baseline,
    baseline,
    batch_key="batch",
    label_key="cell_type",
    baseline_rep="X_pca",
    integrated_rep="X_pca",
    n_neighbors=5,
    run_scib_metrics=False,
)
assert "batch_entropy_mean" in metrics["metric"].tolist()
assert "graph_connectivity" in metrics["metric"].tolist()
PY""",
        ],
        cwd=TEMPLATE_DIR,
        check=True,
    )

    upstream_templates = [
        {
            "id": "scrna_prep",
            "outputs": {
                "scrna_prep_h5ad": "/tmp/results/adata.prep.h5ad",
                "integrated_h5ad": "/tmp/results/adata.integrated.h5ad",
                "h5ad_outputs": ["/tmp/results/adata.prep.h5ad", "/tmp/results/adata.integrated.h5ad"],
                "results_dir": "/tmp/results",
            },
        }
    ]
    ctx = FakeContext(upstream_templates)
    assert load_function("get_scrna_integrate_input_h5ad")(ctx) == "/tmp/results/adata.prep.h5ad"
    assert load_function("get_scrna_integrate_input_source_template")(ctx) == "scrna_prep"

    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    qmd_text = (TEMPLATE_DIR / "qc.qmd").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "assets" / "software_versions_spec.yaml").read_text(encoding="utf-8")

    assert "id: scrna_integrate" in template_text
    assert 'exec python3 "${script_dir}/run.py"' in run_sh_text
    assert "quarto" in run_py_text
    assert "qc.qmd" in run_py_text
    assert 'title: "scRNA Integration QC"' in qmd_text
    assert "compare_baseline_and_integrated" in qmd_text
    assert "unintegrated baseline" in readme_text.lower()
    assert "integration_method" in spec_text
    pack_text = (TEMPLATE_DIR.parent.parent / "linkar_pack.yaml").read_text(encoding="utf-8")
    pack_data = yaml.safe_load(pack_text)
    params = pack_data["templates"]["scrna_integrate"]["params"]
    assert params["input_h5ad"]["function"] == "get_scrna_integrate_input_h5ad"
    assert params["input_source_template"]["function"] == "get_scrna_integrate_input_source_template"
    print("scrna_integrate template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
