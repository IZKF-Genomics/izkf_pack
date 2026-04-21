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
    run_module = load_module(TEMPLATE_DIR / "run.py", "test_scverse_scrna_annotate_run")
    with tempfile.TemporaryDirectory(prefix="linkar-scverse-scrna-annotate-test-") as tmp:
        project_dir = Path(tmp) / "260421_scRNA_Annotation"
        results_dir = Path(tmp) / "results"
        (TEMPLATE_DIR / "config").mkdir(exist_ok=True)
        results_dir.mkdir()
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(yaml.safe_dump({}, sort_keys=False), encoding="utf-8")

        params = {
            "input_h5ad": "/tmp/input.h5ad",
            "input_source_template": "scverse_scrna_prep",
            "annotation_method": "celltypist",
            "celltypist_model": "Immune_All_Low.pkl",
            "celltypist_mode": "best_match",
            "celltypist_p_thres": "0.5",
            "use_gpu": "false",
            "cluster_key": "leiden",
            "batch_key": "batch",
            "condition_key": "condition",
            "sample_id_key": "sample_id",
            "sample_label_key": "sample_display",
            "majority_vote_min_fraction": "0.6",
            "confidence_threshold": "0.5",
            "unknown_label": "Unknown",
            "predicted_label_key": "predicted_label",
            "final_label_key": "final_label",
            "marker_file": "",
            "rank_top_markers": "5",
            "random_seed": "0",
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

        assert 'annotation_method = "celltypist"' in config_text
        assert 'celltypist_model = "Immune_All_Low.pkl"' in config_text
        assert 'cluster_key = "leiden"' in config_text
        assert run_info["params"]["project_name"] == "260421_scRNA_Annotation"
        assert run_info["params"]["annotation_method"] == "celltypist"
        assert run_info["params"]["use_gpu"] is False

        assert_fails(
            [sys.executable, str(TEMPLATE_DIR / "run.py")],
            "Set INPUT_H5AD",
            env={**os.environ, "LINKAR_PACK_ROOT": str(TEMPLATE_DIR.parent.parent)},
        )
        assert_fails(
            [sys.executable, str(TEMPLATE_DIR / "run.py")],
            "Set CELLTYPIST_MODEL",
            env={
                **os.environ,
                "LINKAR_PACK_ROOT": str(TEMPLATE_DIR.parent.parent),
                "INPUT_H5AD": "/tmp/input.h5ad",
                "CLUSTER_KEY": "leiden",
            },
        )

    subprocess.run(
        [
            "bash",
            "-lc",
            """pixi run python - <<'PY'
from pathlib import Path
import tempfile
import sys
sys.path.insert(0, str(Path("lib").resolve()))
import numpy as np
import pandas as pd
import scanpy as sc
import anndata as ad
import celltypist
from types import SimpleNamespace

from annotation_io import load_marker_sets, normalize_text_series, resolve_gene_symbols
from annotation_methods import apply_cluster_suggestions, prepare_celltypist_adata, run_celltypist_annotation, summarize_cluster_predictions
from annotation_review import merge_marker_review, score_marker_sets

rng = np.random.default_rng(0)
counts = rng.poisson(2.0, size=(24, 6))
adata = ad.AnnData(X=counts.astype(float))
adata.var_names = ["CD3D", "CD3E", "MS4A1", "CD79A", "NKG7", "LYZ"]
adata.obs["cluster"] = ["0"] * 8 + ["1"] * 8 + ["2"] * 8
adata.obs["train_label"] = ["T_cells"] * 8 + ["B_cells"] * 8 + ["Myeloid"] * 8
adata.obs["sample_id"] = ["s1"] * 12 + ["s2"] * 12
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

labels = pd.DataFrame(
    {
        "predicted_labels": ["T_cells"] * 8 + ["B_cells"] * 8 + ["Myeloid"] * 8,
    },
    index=adata.obs_names,
)
probability_matrix = pd.DataFrame(
    {
        "T_cells": [0.95] * 8 + [0.02] * 16,
        "B_cells": [0.02] * 8 + [0.94] * 8 + [0.03] * 8,
        "Myeloid": [0.03] * 16 + [0.96] * 8,
    },
    index=adata.obs_names,
)
original_annotate = celltypist.annotate
celltypist.annotate = lambda *args, **kwargs: SimpleNamespace(predicted_labels=labels, probability_matrix=probability_matrix)
try:
    prediction_df, probability_matrix = run_celltypist_annotation(
        adata,
        model="dummy_model.pkl",
        mode="best_match",
        p_thres=0.5,
        use_gpu=False,
        predicted_label_key="predicted_label",
    )
finally:
    celltypist.annotate = original_annotate
assert "predicted_label" in prediction_df.columns
assert "predicted_confidence" in prediction_df.columns
assert prediction_df.shape[0] == adata.n_obs
assert probability_matrix.shape[0] == adata.n_obs

summary, top_labels = summarize_cluster_predictions(
    pd.DataFrame(
        {
            "cluster": adata.obs["cluster"].to_numpy(),
            "predicted_label": prediction_df["predicted_label"].to_numpy(),
            "predicted_confidence": prediction_df["predicted_confidence"].to_numpy(),
        }
    ),
    cluster_key="cluster",
    predicted_label_key="predicted_label",
    confidence_key="predicted_confidence",
    min_fraction=0.3,
    confidence_threshold=0.0,
    unknown_label="Unknown",
    top_n=3,
)
assert "cluster_suggested_label" in summary.columns
assert "annotation_status" in summary.columns
assert not top_labels.empty

obs = pd.DataFrame(
    {
        "cluster": adata.obs["cluster"].to_numpy(),
        "predicted_label": prediction_df["predicted_label"].to_numpy(),
        "predicted_confidence": prediction_df["predicted_confidence"].to_numpy(),
        "sample_id": adata.obs["sample_id"].to_numpy(),
        "sample_display": adata.obs["sample_id"].to_numpy(),
        "batch": ["b1"] * adata.n_obs,
        "condition": ["c1"] * adata.n_obs,
    }
)
annotated = apply_cluster_suggestions(obs, summary, cluster_key="cluster", final_label_key="final_label", unknown_label="Unknown")
assert "final_label" in annotated.columns

with tempfile.TemporaryDirectory() as tmp:
    marker_file = Path(tmp) / "markers.yaml"
    marker_file.write_text("T_cells:\\n  - CD3D\\n  - CD3E\\nB_cells:\\n  - MS4A1\\n  - CD79A\\n", encoding="utf-8")
    marker_sets = load_marker_sets(str(marker_file))
    assert marker_sets["T_cells"] == ["CD3D", "CD3E"]
    marker_summary, marker_long = score_marker_sets(adata, marker_sets, cluster_key="cluster")
    assert not marker_long.empty
    merged = merge_marker_review(summary, marker_summary)
    assert "marker_suggested_label" in merged.columns

normalized = normalize_text_series(pd.Series([None, np.nan, "", " nan ", "treated"]), fallback="unknown")
assert normalized.tolist() == ["unknown", "unknown", "unknown", "unknown", "treated"]
prepared = prepare_celltypist_adata(adata)
assert prepared.var_names.tolist() == adata.var_names.tolist()
assert resolve_gene_symbols(pd.DataFrame(index=adata.var_names), adata.var_names).tolist() == adata.var_names.tolist()
PY""",
        ],
        cwd=TEMPLATE_DIR,
        check=True,
    )

    upstream_templates = [
        {
            "id": "scverse_scrna_prep",
            "outputs": {
                "scrna_prep_h5ad": "/tmp/results/adata.prep.h5ad",
            },
        },
        {
            "id": "scverse_scrna_integrate",
            "outputs": {
                "integrated_h5ad": "/tmp/results/adata.integrated.h5ad",
            },
        },
    ]
    ctx = FakeContext(upstream_templates)
    assert load_function("get_scrna_annotate_input_h5ad")(ctx) == "/tmp/results/adata.prep.h5ad"
    assert load_function("get_scrna_annotate_input_source_template")(ctx) == "scverse_scrna_prep"

    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    qmd_text = (TEMPLATE_DIR / "annotation.qmd").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "assets" / "software_versions_spec.yaml").read_text(encoding="utf-8")

    assert "id: scverse_scrna_annotate" in template_text
    assert 'exec python3 "${script_dir}/run.py"' in run_sh_text
    assert "quarto" in run_py_text
    assert "annotation.qmd" in run_py_text
    assert 'title: "scRNA Annotation Review"' in qmd_text
    assert "run_celltypist_annotation" in qmd_text
    assert "cluster_suggested_label" in qmd_text
    assert "CellTypist" in readme_text
    assert "celltypist_model" in spec_text
    pack_text = (TEMPLATE_DIR.parent.parent / "linkar_pack.yaml").read_text(encoding="utf-8")
    pack_data = yaml.safe_load(pack_text)
    params = pack_data["templates"]["scverse_scrna_annotate"]["params"]
    assert params["input_h5ad"]["function"] == "get_scrna_annotate_input_h5ad"
    assert params["input_source_template"]["function"] == "get_scrna_annotate_input_source_template"
    print("scverse_scrna_annotate template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
