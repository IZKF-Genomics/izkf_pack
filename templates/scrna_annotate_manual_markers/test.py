#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


TEMPLATE_DIR = Path(__file__).resolve().parent


def load_run_module():
    sys.path.insert(0, str(TEMPLATE_DIR))
    spec = importlib.util.spec_from_file_location("scrna_annotate_manual_markers_run", TEMPLATE_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_tiny_h5ad(path: Path) -> None:
    adata = ad.AnnData(
        X=sparse.csr_matrix(
            np.array(
                [
                    [8, 7, 0, 0],
                    [7, 6, 0, 0],
                    [0, 0, 8, 7],
                    [0, 0, 7, 6],
                ],
                dtype=np.float32,
            )
        ),
        obs=pd.DataFrame(
            {"leiden": ["0", "0", "1", "1"], "sample_id": ["WT", "WT", "Mut", "Mut"]},
            index=[f"cell{i}" for i in range(4)],
        ),
        var=pd.DataFrame(index=["Lyz2", "Csf1r", "Cd3d", "Cd3e"]),
    )
    adata.obsm["X_umap"] = np.array([[0, 0], [0.1, 0], [2, 2], [2.1, 2]], dtype=np.float32)
    adata.write_h5ad(path)


def test_read_legacy_marker_catalog() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "marker_genes.csv"
        path.write_text("Macrophage,Lyz2,feature_1,Gene Expression\nT cell,Cd3e,feature_2,Gene Expression\n")
        entries = run.read_marker_catalog(path)
        assert entries[0].cell_type == "Macrophage"
        assert entries[0].gene_symbol == "Lyz2"
        assert entries[0].marker_role == "positive"


def test_manual_marker_scoring_and_predictions() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_h5ad = tmp_path / "input.h5ad"
        write_tiny_h5ad(input_h5ad)
        entries = [
            run.ManualMarker("Macrophage", "Lyz2", "positive", "user", "cite", "local"),
            run.ManualMarker("Macrophage", "Csf1r", "positive", "user", "cite", "local"),
            run.ManualMarker("T cell", "Cd3d", "positive", "user", "cite", "local"),
            run.ManualMarker("T cell", "Cd3e", "positive", "user", "cite", "local"),
        ]
        score_rows, catalog_rows, warnings = run.score_manual_markers(
            input_h5ad=input_h5ad,
            entries=entries,
            cluster_key="leiden",
            expression_layer="X",
            score_method="scanpy_score_genes",
            min_score_margin=0.15,
        )
        assert not warnings
        assert len(catalog_rows) == 4
        predictions = run.cluster_predictions_from_scores(score_rows, {"0": 2, "1": 2})
        labels = {pred["cluster_id"]: pred["top_label"] for pred in predictions}
        assert labels["0"] == "Macrophage"
        assert labels["1"] == "T cell"
        assert predictions[0]["candidates"][0]["provider_score_name"] == "manual_marker_cluster_mean_zscore"


def test_write_annotated_h5ad() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_h5ad = tmp_path / "input.h5ad"
        output_h5ad = tmp_path / "annotated.h5ad"
        write_tiny_h5ad(input_h5ad)
        predictions = [
            {
                "cluster_id": "0",
                "top_label": "Macrophage",
                "confidence_bucket": "high",
                "review_status": "review candidate",
                "candidates": [
                    {
                        "provider_score": 1.2,
                        "evidence_items": [{"score_margin": 0.6, "matched_genes": ["Lyz2", "Csf1r"]}],
                    }
                ],
            },
            {
                "cluster_id": "1",
                "top_label": "T cell",
                "confidence_bucket": "high",
                "review_status": "review candidate",
                "candidates": [
                    {
                        "provider_score": 1.1,
                        "evidence_items": [{"score_margin": 0.5, "matched_genes": ["Cd3d", "Cd3e"]}],
                    }
                ],
            },
        ]
        run.write_annotated_h5ad(
            input_h5ad=input_h5ad,
            output_h5ad=output_h5ad,
            cluster_predictions=predictions,
            params={"cluster_key": "leiden"},
        )
        result = ad.read_h5ad(output_h5ad)
        assert list(result.obs["scrna_annotate_manual_markers_label"].astype(str)) == ["Macrophage", "Macrophage", "T cell", "T cell"]
        assert result.uns["scrna_annotate_manual_markers"]["schema_version"] == "izkf_annotation_result.v1"


def test_resolve_input_h5ad_from_scrna_prep() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        input_h5ad = project_dir / "scrna_prep" / "results" / "adata.prep.h5ad"
        input_h5ad.parent.mkdir(parents=True)
        input_h5ad.write_text("placeholder", encoding="utf-8")
        old_project_dir = run.PROJECT_DIR
        run.PROJECT_DIR = project_dir
        try:
            params = {"input_h5ad": "", "input_source_template": ""}
            resolved = run.resolve_input_h5ad(params)
        finally:
            run.PROJECT_DIR = old_project_dir
        assert resolved == input_h5ad.resolve()
        assert params["input_source_template"] == "scrna_prep"


def main() -> int:
    test_read_legacy_marker_catalog()
    test_manual_marker_scoring_and_predictions()
    test_write_annotated_h5ad()
    test_resolve_input_h5ad_from_scrna_prep()
    print("scrna_annotate_manual_markers tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
