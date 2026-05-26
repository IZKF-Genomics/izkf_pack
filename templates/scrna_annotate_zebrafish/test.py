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
    spec = importlib.util.spec_from_file_location("scrna_annotate_zebrafish_run", TEMPLATE_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_catalog_scoring() -> None:
    run = load_run_module()
    markers = [
        {"cluster_id": "0", "rank": 1, "gene": "cd3d", "score": 8, "log2fc": 2.1, "pval_adj": 0.001, "strength": "strong"},
        {"cluster_id": "0", "rank": 2, "gene": "cd3e", "score": 7, "log2fc": 1.8, "pval_adj": 0.002, "strength": "strong"},
        {"cluster_id": "0", "rank": 3, "gene": "trac", "score": 6, "log2fc": 1.5, "pval_adj": 0.003, "strength": "strong"},
    ]
    entries = [
        run.CatalogEntry("test", "zebrafish", "NCBITaxon:7955", "", "larval", "T cell", "cd3d", "user", "cite", "example"),
        run.CatalogEntry("test", "zebrafish", "NCBITaxon:7955", "", "larval", "T cell", "cd3e", "user", "cite", "example"),
        run.CatalogEntry("test", "zebrafish", "NCBITaxon:7955", "", "larval", "T cell", "trac", "user", "cite", "example"),
    ]
    background_genes = {"cd3d", "cd3e", "trac", "mpeg1", "lcp1", "mpx", "pax6a", "gfap", "vim"}
    rows = run.score_catalog(
        markers,
        entries,
        min_log2fc=0.25,
        fdr_threshold=0.05,
        background_genes=background_genes,
    )
    assert rows[0]["cell_type"] == "T cell"
    assert rows[0]["species"] == "zebrafish"
    assert float(rows[0]["pval_adj"]) <= 0.05
    predictions = run.cluster_predictions_from_matches(rows, {"0": 10})
    assert predictions[0]["top_label"] == "T cell"


def test_read_catalog_requires_columns() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.tsv"
        path.write_text("cell_type\tgene_symbol\nT cell\tcd3d\n")
        try:
            run.read_catalog(path)
        except SystemExit as exc:
            assert "missing required columns" in str(exc)
        else:
            raise AssertionError("bad catalog should fail")


def test_safe_excel_sheet_name() -> None:
    run = load_run_module()
    assert run.safe_excel_sheet_name("a/b*c?") == "a_b_c_"
    assert len(run.safe_excel_sheet_name("x" * 40)) == 31


def test_write_annotated_h5ad() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_h5ad = tmp_path / "input.h5ad"
        output_h5ad = tmp_path / "annotated.h5ad"
        adata = ad.AnnData(
            X=sparse.csr_matrix(np.array([[1, 0], [0, 2], [3, 0]], dtype=np.float32)),
            obs=pd.DataFrame(
                {
                    "leiden": ["0", "0", "1"],
                    "sample_id": ["Control_WT_1", "Cut_Mut_1", "Cut_WT_2"],
                },
                index=["cell1", "cell2", "cell3"],
            ),
            var=pd.DataFrame(index=["gene_a", "gene_b"]),
        )
        adata.layers["counts"] = adata.X.copy()
        adata.obsm["X_umap"] = np.array([[0, 0], [1, 1], [2, 2]], dtype=np.float32)
        adata.write_h5ad(input_h5ad)
        predictions = [
            {
                "cluster_id": "0",
                "top_label": "neuron",
                "confidence_bucket": "medium",
                "candidates": [
                    {
                        "provider_score": 10.0,
                        "evidence": {"matched_genes": ["gene_a", "gene_b"]},
                    }
                ],
            },
            {"cluster_id": "1", "top_label": None, "confidence_bucket": "unknown", "candidates": []},
        ]
        run.write_annotated_h5ad(
            input_h5ad=input_h5ad,
            output_h5ad=output_h5ad,
            cluster_predictions=predictions,
            params={"cluster_key": "leiden", "sample_key": "sample_id"},
        )
        result = ad.read_h5ad(output_h5ad)
        assert list(result.obs["scrna_annotate_zebrafish_label"].astype(str)) == ["neuron", "neuron", "no catalog match"]
        assert list(result.obs["scrna_annotate_zebrafish_genotype"].astype(str)) == ["WT", "KO", "WT"]
        assert list(result.obs["scrna_annotate_zebrafish_treatment"].astype(str)) == ["Control", "Cut", "Cut"]
        assert result.uns["scrna_annotate_zebrafish"]["label_column"] == "scrna_annotate_zebrafish_label"
        assert result.uns["scrna_annotate_zebrafish"]["schema_version"] == "izkf_annotation_result.v1"
        assert "cluster_predictions_json" in result.uns["scrna_annotate_zebrafish"]


def test_software_versions_contract() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "software_versions:" in template_text
    assert "path: results/software_versions.json" in template_text
    assert 'python3 "${pack_root}/functions/software_versions.py"' in run_sh_text
    assert '--spec "${script_dir}/software_versions_spec.yaml"' in run_sh_text
    assert 'linkar collect "${script_dir}"' in run_sh_text
    assert "marker_catalog" in spec_text


def main() -> int:
    test_catalog_scoring()
    test_read_catalog_requires_columns()
    test_safe_excel_sheet_name()
    test_write_annotated_h5ad()
    test_software_versions_contract()
    print("scrna_annotate_zebrafish tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
