#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


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


def main() -> int:
    test_catalog_scoring()
    test_read_catalog_requires_columns()
    test_safe_excel_sheet_name()
    print("scrna_annotate_zebrafish tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
