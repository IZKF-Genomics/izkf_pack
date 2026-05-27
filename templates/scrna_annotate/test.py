#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


def load_core_module():
    sys.path.insert(0, str(TEMPLATE_DIR))
    spec = importlib.util.spec_from_file_location("scrna_annotate_marker_core", TEMPLATE_DIR / "providers" / "marker_based" / "core.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_provider_runner_module():
    sys.path.insert(0, str(TEMPLATE_DIR))
    spec = importlib.util.spec_from_file_location("scrna_annotate_provider_runner", TEMPLATE_DIR / "lib" / "provider_runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_marker_catalog_module():
    sys.path.insert(0, str(TEMPLATE_DIR))
    spec = importlib.util.spec_from_file_location("scrna_annotate_marker_catalog_core", TEMPLATE_DIR / "providers" / "marker_catalog" / "core.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_marker_signature_scoring() -> None:
    run = load_core_module()
    markers = [
        run.MarkerGene("0", 1, "CD3D", 8.0, 2.1, 0.001),
        run.MarkerGene("0", 2, "CD3E", 7.5, 1.8, 0.002),
        run.MarkerGene("0", 3, "TRAC", 6.2, 1.4, 0.003),
        run.MarkerGene("0", 4, "MS4A1", 2.0, 0.1, 0.2),
        run.MarkerGene("1", 1, "MS4A1", 8.0, 2.0, 0.001),
        run.MarkerGene("1", 2, "CD79A", 7.0, 1.5, 0.002),
        run.MarkerGene("1", 3, "CD79B", 6.0, 1.2, 0.004),
    ]
    rows = run.score_marker_signatures(markers, min_log2fc=0.25)
    top_by_cluster = {}
    for row in rows:
        top_by_cluster.setdefault(row["cluster_id"], row)
    assert top_by_cluster["0"]["label"] == "T cell"
    assert top_by_cluster["1"]["label"] == "B cell"
    assert top_by_cluster["0"]["confidence_bucket"] in {"medium", "high"}


def test_cluster_prediction_contract() -> None:
    run = load_core_module()
    markers = [
        run.MarkerGene("0", 1, "CD3D", 8.0, 2.1, 0.001),
        run.MarkerGene("0", 2, "CD3E", 7.5, 1.8, 0.002),
        run.MarkerGene("0", 3, "TRAC", 6.2, 1.4, 0.003),
    ]
    marker_rows = run.marker_table_rows(markers, min_log2fc=0.25)
    signature_rows = run.score_marker_signatures(markers, min_log2fc=0.25)
    predictions = run.cluster_predictions_from_signatures(signature_rows, marker_rows, {"0": 10})
    assert predictions[0]["cluster_id"] == "0"
    assert predictions[0]["top_label"] == "T cell"
    assert predictions[0]["candidates"][0]["provider_score_name"] == "builtin_marker_signature_overlap"
    assert "top_markers" in predictions[0]["candidates"][0]["evidence"]
    assert predictions[0]["candidates"][0]["evidence"]["score_type"] == "heuristic_overlap"


def test_run_on_tiny_h5ad_when_scanpy_available() -> None:
    if importlib.util.find_spec("scanpy") is None or importlib.util.find_spec("anndata") is None:
        return

    import anndata as ad
    import numpy as np
    import pandas as pd
    import scipy.sparse as sp

    run = load_core_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        input_h5ad = tmpdir / "tiny.h5ad"
        results_dir = tmpdir / "results"
        genes = ["CD3D", "CD3E", "TRAC", "MS4A1", "CD79A", "CD79B"]
        obs = pd.DataFrame({"leiden": ["0"] * 8 + ["1"] * 8}, index=[f"cell{i}" for i in range(16)])
        x = np.array(
            [[8, 7, 6, 1, 1, 1]] * 8
            + [[1, 1, 1, 8, 7, 6]] * 8,
            dtype=float,
        )
        adata = ad.AnnData(sp.csr_matrix(x), obs=obs, var=pd.DataFrame(index=genes))
        adata.write_h5ad(input_h5ad)

        payload = run.run_provider(
            input_h5ad,
            {"cluster_key": "leiden", "expression_layer": "X", "gene_id_type": "gene_symbols"},
            {"top_n_markers": 5, "min_log2fc": 0.25, "expression_layer": "X"},
            template_dir=TEMPLATE_DIR,
            results_dir=results_dir,
        )

        assert payload["status"]["state"] in {"completed", "completed_with_warnings"}
        assert (results_dir / "providers" / "marker_based" / "annotation_result.json").exists()
        assert payload["cluster_predictions"]


def test_zebrafish_warning_is_explicit() -> None:
    run = load_core_module()
    warnings: list[str] = []
    run.validate_marker_inputs(
        {"organism": "zebrafish", "gene_id_type": "gene_symbols", "tissue": "brain"},
        "X",
        warnings,
    )
    assert any("zebrafish" in warning.lower() for warning in warnings)
    assert any("human" in warning.lower() for warning in warnings)


def test_zebrafish_does_not_use_human_signatures() -> None:
    run = load_core_module()
    warnings: list[str] = []
    source = run.built_in_signature_source_for_dataset({"organism": "zebrafish"}, warnings)
    markers = [
        run.MarkerGene("0", 1, "CD3D", 8.0, 2.1, 0.001),
        run.MarkerGene("0", 2, "CD3E", 7.5, 1.8, 0.002),
        run.MarkerGene("0", 3, "TRAC", 6.2, 1.4, 0.003),
    ]
    rows = run.score_marker_signatures(markers, min_log2fc=0.25, signature_source=source)
    assert source is None
    assert rows == []


def test_missing_tissue_is_warning_not_error() -> None:
    run = load_core_module()
    warnings: list[str] = []
    run.validate_marker_inputs(
        {"organism": "human", "gene_id_type": "gene_symbols", "tissue": ""},
        "normalized",
        warnings,
    )
    assert any("tissue is not set" in warning.lower() for warning in warnings)


def test_provider_runner_marks_unimplemented_enabled_provider() -> None:
    runner = load_provider_runner_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        results = runner.run_configured_providers(
            input_h5ad=tmpdir / "input.h5ad",
            dataset={"cluster_key": "leiden"},
            providers={"celltypist": {"enabled": True}},
            template_dir=TEMPLATE_DIR,
            results_dir=tmpdir / "results",
            progress=lambda _message: None,
        )
        assert results[0]["provider"]["id"] == "celltypist"
        assert results[0]["status"]["state"] == "needs_config"
        assert (tmpdir / "results" / "providers" / "celltypist" / "annotation_result.json").exists()


def test_marker_catalog_scores_matching_zebrafish_catalog() -> None:
    catalog = load_marker_catalog_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        results_dir = tmpdir / "results"
        marker_dir = results_dir / "providers" / "marker_based" / "tables"
        marker_dir.mkdir(parents=True)
        (marker_dir / "differential_markers.csv").write_text(
            "cluster_id,rank,gene,score,log2fc,pval_adj,strength\n"
            "0,1,cd3d,8,2.1,0.001,strong\n"
            "0,2,cd3e,7,1.8,0.002,strong\n"
            "0,3,trac,6,1.5,0.003,strong\n"
        )
        catalog_path = tmpdir / "zebrafish.tsv"
        catalog_path.write_text(
            "catalog_id\tspecies\torganism_id\ttissue\tstage\tcell_type\tgene_symbol\tsource\tcitation\tevidence\n"
            "test\tzebrafish\tNCBITaxon:7955\t\tlarval\tT cell\tcd3d\tuser\tcite\texample\n"
            "test\tzebrafish\tNCBITaxon:7955\t\tlarval\tT cell\tcd3e\tuser\tcite\texample\n"
            "test\tzebrafish\tNCBITaxon:7955\t\tlarval\tT cell\ttrac\tuser\tcite\texample\n"
        )
        payload = catalog.run_provider(
            tmpdir / "input.h5ad",
            {"organism": "zebrafish", "cluster_key": "leiden"},
            {"catalog_path": str(catalog_path), "species": "zebrafish", "min_matched_genes": 2, "min_log2fc": 0.25},
            template_dir=TEMPLATE_DIR,
            results_dir=results_dir,
        )
        assert payload["status"]["state"] == "completed"
        assert payload["cluster_predictions"][0]["top_label"] == "T cell"
        assert payload["cluster_predictions"][0]["candidates"][0]["evidence"]["species"] == "zebrafish"


def test_marker_catalog_refuses_species_mismatch() -> None:
    catalog = load_marker_catalog_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        results_dir = tmpdir / "results"
        marker_dir = results_dir / "providers" / "marker_based" / "tables"
        marker_dir.mkdir(parents=True)
        (marker_dir / "differential_markers.csv").write_text("cluster_id,rank,gene,score,log2fc,pval_adj,strength\n")
        catalog_path = tmpdir / "human.tsv"
        catalog_path.write_text(
            "catalog_id\tspecies\torganism_id\ttissue\tstage\tcell_type\tgene_symbol\tsource\tcitation\tevidence\n"
            "test\thuman\tNCBITaxon:9606\t\t\tT cell\tCD3D\tuser\tcite\texample\n"
        )
        payload = catalog.run_provider(
            tmpdir / "input.h5ad",
            {"organism": "zebrafish", "cluster_key": "leiden"},
            {"catalog_path": str(catalog_path), "species": "human"},
            template_dir=TEMPLATE_DIR,
            results_dir=results_dir,
        )
        assert payload["status"]["state"] == "needs_config"
    assert any("does not match" in item for item in payload["status"]["missing_config"])


def test_software_versions_contract() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "software_versions:" in template_text
    assert "path: results/software_versions.json" in template_text
    assert 'python3 "${pack_root}/functions/software_versions.py"' in run_sh_text
    assert '--spec "${script_dir}/software_versions_spec.yaml"' in run_sh_text
    assert 'linkar collect "${script_dir}"' in run_sh_text
    assert 'rm -rf "${script_dir}/.pixi"' in run_sh_text
    assert 'rm -rf "${script_dir}/__pycache__"' in run_sh_text
    assert "provider_preset" in spec_text


def main() -> int:
    for test in [
        test_marker_signature_scoring,
        test_cluster_prediction_contract,
        test_run_on_tiny_h5ad_when_scanpy_available,
        test_zebrafish_warning_is_explicit,
        test_zebrafish_does_not_use_human_signatures,
        test_missing_tissue_is_warning_not_error,
        test_provider_runner_marks_unimplemented_enabled_provider,
        test_marker_catalog_scores_matching_zebrafish_catalog,
        test_marker_catalog_refuses_species_mismatch,
        test_software_versions_contract,
    ]:
        test()
    print("scrna_annotate tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
