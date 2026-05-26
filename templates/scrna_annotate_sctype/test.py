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
    spec = importlib.util.spec_from_file_location("scrna_annotate_sctype_run", TEMPLATE_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sctype_scoring_and_prediction_schema() -> None:
    run = load_run_module()
    markers = [
        {"cluster_id": "0", "rank": 1, "gene": "Lyz2", "score": 8, "log2fc": 2.1, "pval_adj": 0.001, "strength": "strong"},
        {"cluster_id": "0", "rank": 2, "gene": "Csf1r", "score": 7, "log2fc": 1.8, "pval_adj": 0.002, "strength": "strong"},
        {"cluster_id": "0", "rank": 3, "gene": "Cd3e", "score": 6, "log2fc": 1.5, "pval_adj": 0.003, "strength": "strong"},
    ]
    primary_entries = [
        run.CatalogEntry("sctype", "mouse", "NCBITaxon:10090", "Immune system", "Macrophages", "Lyz2", "positive", "ScType", "cite", "db"),
        run.CatalogEntry("sctype", "mouse", "NCBITaxon:10090", "Immune system", "Macrophages", "Csf1r", "positive", "ScType", "cite", "db"),
        run.CatalogEntry("sctype", "mouse", "NCBITaxon:10090", "Immune system", "Macrophages", "Cd3e", "negative", "ScType", "cite", "db"),
        run.CatalogEntry("sctype", "mouse", "NCBITaxon:10090", "Immune system", "T cells", "Cd3e", "positive", "ScType", "cite", "db"),
    ]
    primary_rows = run.score_marker_catalog(markers, primary_entries, min_log2fc=0.25, catalog_role="primary_sctype")
    assert primary_rows[0]["cell_type"] == "Macrophages"
    assert primary_rows[0]["score"] == 1.0
    predictions = run.cluster_predictions_from_candidates(primary_rows, {"0": 10})
    top = predictions[0]["candidates"][0]
    assert predictions[0]["top_label"] == "Macrophages"
    assert "evidence_items" in top
    assert top["evidence_items"][0]["evidence_type"] == "primary_marker_score"
    assert top["provider_score_name"] == "sctype_positive_minus_negative_marker_matches"


def test_read_catalog_requires_columns() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.tsv"
        path.write_text("cell_type\tgene_symbol\nT cell\tCd3d\n")
        try:
            run.read_catalog(path)
        except SystemExit as exc:
            assert "missing required columns" in str(exc)
        else:
            raise AssertionError("bad catalog should fail")


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
            X=sparse.csr_matrix(np.array([[1, 0], [0, 2], [3, 0]], dtype=np.float32)),
            obs=pd.DataFrame({"leiden": ["0", "0", "1"]}, index=["cell1", "cell2", "cell3"]),
            var=pd.DataFrame(index=["Lyz2", "Cd3e"]),
        )
        adata.write_h5ad(input_h5ad)
        predictions = [
            {
                "cluster_id": "0",
                "top_label": "Macrophages",
                "top_label_normalized": "macrophage",
                "confidence_bucket": "medium",
                "review_status": "review candidate",
                "candidates": [
                    {
                        "provider_score": 2.0,
                        "evidence_items": [
                            {
                                "matched_positive_genes": ["Lyz2"],
                                "matched_negative_genes": [],
                            }
                        ],
                    }
                ],
            },
            {"cluster_id": "1", "top_label": None, "confidence_bucket": "unknown", "review_status": "no catalog-supported candidate", "candidates": []},
        ]
        run.write_annotated_h5ad(
            input_h5ad=input_h5ad,
            output_h5ad=output_h5ad,
            cluster_predictions=predictions,
            params={"cluster_key": "leiden"},
        )
        result = ad.read_h5ad(output_h5ad)
        assert list(result.obs["scrna_annotate_sctype_label"].astype(str)) == ["Macrophages", "Macrophages", "no ScType match"]
        assert not [column for column in result.obs.columns if column.startswith("scrna_annotate_sctype_") and "_local_" in column]
        assert result.uns["scrna_annotate_sctype"]["schema_version"] == "izkf_annotation_result.v1"
        assert "cluster_predictions_json" in result.uns["scrna_annotate_sctype"]


def test_software_versions_contract() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "software_versions:" in template_text
    assert "path: results/software_versions.json" in template_text
    assert 'python3 "${pack_root}/functions/software_versions.py"' in run_sh_text
    assert '--spec "${script_dir}/software_versions_spec.yaml"' in run_sh_text
    assert "primary_catalog" in spec_text


def main() -> int:
    test_sctype_scoring_and_prediction_schema()
    test_read_catalog_requires_columns()
    test_resolve_input_h5ad_from_scrna_prep()
    test_write_annotated_h5ad()
    test_software_versions_contract()
    print("scrna_annotate_sctype tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
