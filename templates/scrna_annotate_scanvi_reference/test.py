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
    spec = importlib.util.spec_from_file_location("scrna_annotate_scanvi_reference_run", TEMPLATE_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_harmonize_genes_preserves_query_order() -> None:
    run = load_run_module()
    query = ad.AnnData(X=sparse.csr_matrix(np.ones((2, 4))), var=pd.DataFrame(index=["B", "A", "D", "C"]))
    reference = ad.AnnData(X=sparse.csr_matrix(np.ones((2, 3))), var=pd.DataFrame(index=["A", "B", "C"]))
    assert run.harmonize_genes(query, reference) == ["B", "A", "C"]


def test_cell_prediction_rows_schema() -> None:
    run = load_run_module()
    adata = ad.AnnData(
        X=sparse.csr_matrix(np.ones((2, 2))),
        obs=pd.DataFrame(
            {
                "_izkf_original_cell_id": ["cell1", "cell2"],
                "leiden": ["0", "1"],
                "sample_id": ["s1", "s2"],
            },
            index=["query::cell1", "query::cell2"],
        ),
        var=pd.DataFrame(index=["Gene1", "Gene2"]),
    )
    predictions = pd.Series(["Cardiomyocyte", "Fibroblast"], index=adata.obs_names)
    probabilities = pd.DataFrame(
        {
            "Cardiomyocyte": [0.9, 0.2],
            "Fibroblast": [0.1, 0.7],
            "Endothelial": [0.0, 0.1],
        },
        index=adata.obs_names,
    )
    rows = run.cell_prediction_rows(
        adata,
        predictions,
        probabilities,
        {"cluster_key": "leiden", "sample_key": "sample_id", "prediction_min_probability": 0.6, "top_n_candidates": 3},
    )
    assert rows[0]["cell_id"] == "cell1"
    assert rows[0]["candidate_1"] == "Cardiomyocyte"
    assert rows[0]["confidence_bucket"] == "high"
    assert rows[1]["candidate_1"] == "Fibroblast"
    assert rows[1]["confidence_bucket"] == "medium"


def test_cluster_summary_flags_mixed_cluster() -> None:
    run = load_run_module()
    rows = [
        {"cluster_id": "0", "top_label": "A", "max_probability": 0.8},
        {"cluster_id": "0", "top_label": "A", "max_probability": 0.7},
        {"cluster_id": "0", "top_label": "B", "max_probability": 0.8},
        {"cluster_id": "0", "top_label": "B", "max_probability": 0.7},
    ]
    summary = run.cluster_summary_rows(rows, "leiden")
    assert summary[0]["top_label_fraction"] == 0.5
    assert summary[0]["review_status"] == "mixed cluster"


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


def test_write_annotated_h5ad() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_h5ad = tmp_path / "input.h5ad"
        output_h5ad = tmp_path / "annotated.h5ad"
        adata = ad.AnnData(
            X=sparse.csr_matrix(np.array([[1, 0], [0, 2]], dtype=np.float32)),
            obs=pd.DataFrame({"leiden": ["0", "1"]}, index=["cell1", "cell2"]),
            var=pd.DataFrame(index=["Gene1", "Gene2"]),
        )
        adata.write_h5ad(input_h5ad)
        cell_rows = [
            {
                "cell_id": "cell1",
                "top_label": "Cardiomyocyte",
                "confidence_bucket": "high",
                "max_probability": 0.91,
                "entropy": 0.2,
                "review_status": "review candidate",
                "candidate_1": "Cardiomyocyte",
                "candidate_1_probability": 0.91,
            },
            {
                "cell_id": "cell2",
                "top_label": "Fibroblast",
                "confidence_bucket": "medium",
                "max_probability": 0.7,
                "entropy": 0.4,
                "review_status": "review candidate",
                "candidate_1": "Fibroblast",
                "candidate_1_probability": 0.7,
            },
        ]
        run.write_annotated_h5ad(
            input_h5ad=input_h5ad,
            output_h5ad=output_h5ad,
            cell_rows=cell_rows,
            latent=np.ones((2, 3)),
            umap=np.ones((2, 2)),
            params={"reference_name": "test_reference", "reference_label_key": "cell_type"},
        )
        result = ad.read_h5ad(output_h5ad)
        assert list(result.obs["scrna_annotate_scanvi_reference_label"].astype(str)) == ["Cardiomyocyte", "Fibroblast"]
        assert "X_scANVI" in result.obsm
        assert "X_scANVI_umap" in result.obsm
        assert result.uns["scrna_annotate_scanvi_reference"]["schema_version"] == "izkf_annotation_result.v1"


def test_software_versions_contract() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "software_versions:" in template_text
    assert "path: results/software_versions.json" in template_text
    assert 'python3 "${pack_root}/functions/software_versions.py"' in run_sh_text
    assert '--spec "${script_dir}/software_versions_spec.yaml"' in run_sh_text
    assert "reference_h5ad" in spec_text


def main() -> int:
    test_harmonize_genes_preserves_query_order()
    test_cell_prediction_rows_schema()
    test_cluster_summary_flags_mixed_cluster()
    test_resolve_input_h5ad_from_scrna_prep()
    test_write_annotated_h5ad()
    test_software_versions_contract()
    print("scrna_annotate_scanvi_reference tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
