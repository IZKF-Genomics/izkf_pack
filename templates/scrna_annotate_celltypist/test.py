#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


def load_run_module():
    sys.path.insert(0, str(TEMPLATE_DIR))
    spec = importlib.util.spec_from_file_location("scrna_annotate_celltypist_run", TEMPLATE_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_species_normalization() -> None:
    run = load_run_module()
    assert run.normalize_species("Mus musculus") == "mouse"
    assert run.normalize_species("NCBITaxon:9606") == "human"
    assert run.default_organism_id("mouse") == "NCBITaxon:10090"


def test_model_selection_prefers_matching_tissue_and_species() -> None:
    run = load_run_module()
    rows = [
        {"model": "Immune_All_Low.pkl", "description": "Human immune cells", "inferred_species": "human", "score": 0, "selected": ""},
        {"model": "Mouse_Whole_Brain.pkl", "description": "Mouse brain", "inferred_species": "mouse", "score": 0, "selected": ""},
        {"model": "Human_Heart.pkl", "description": "Human heart atlas", "inferred_species": "human", "score": 0, "selected": ""},
        {"model": "Mouse_Heart.pkl", "description": "Mouse heart atlas", "inferred_species": "mouse", "score": 0, "selected": ""},
    ]
    selected = run.select_model("auto", rows, organism="mouse", tissue="heart")
    assert selected == "Mouse_Heart.pkl"


def test_model_selection_prefers_cross_species_heart_over_generic_mouse() -> None:
    run = load_run_module()
    rows = [
        {"model": "Immune_All_Low.pkl", "description": "Human immune cells", "inferred_species": "human", "score": 0, "selected": ""},
        {"model": "Mouse_Whole_Brain.pkl", "description": "Mouse brain", "inferred_species": "mouse", "score": 0, "selected": ""},
        {"model": "Human_Heart.pkl", "description": "Human heart atlas", "inferred_species": "human", "score": 0, "selected": ""},
    ]
    selected = run.select_model("auto", rows, organism="mouse", tissue="heart")
    assert selected == "Human_Heart.pkl"
    assert rows[2]["score"] > rows[1]["score"]


def test_model_selection_uses_explicit_model() -> None:
    run = load_run_module()
    selected = run.select_model("Immune_All_Low.pkl", [], organism="mouse", tissue="heart")
    assert selected == "Immune_All_Low.pkl"


def test_resolve_input_h5ad_prefers_scrna_prep() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        prep_h5ad = project_dir / "scrna_prep" / "results" / "adata.prep.h5ad"
        annotate_h5ad = project_dir / "scrna_annotate_sctype" / "results" / "adata.annotated.h5ad"
        prep_h5ad.parent.mkdir(parents=True)
        annotate_h5ad.parent.mkdir(parents=True)
        prep_h5ad.write_text("prep", encoding="utf-8")
        annotate_h5ad.write_text("annotation", encoding="utf-8")
        old_project_dir = run.PROJECT_DIR
        run.PROJECT_DIR = project_dir
        try:
            params = {"input_h5ad": "", "input_source_template": ""}
            resolved = run.resolve_input_h5ad(params)
        finally:
            run.PROJECT_DIR = old_project_dir
        assert resolved == prep_h5ad.resolve()
        assert params["input_source_template"] == "scrna_prep"


def test_cluster_summary() -> None:
    run = load_run_module()
    rows = [
        {"cluster_id": "0", "top_label": "Fibroblast"},
        {"cluster_id": "0", "top_label": "Fibroblast"},
        {"cluster_id": "0", "top_label": "Endothelial"},
    ]
    summary = run.cluster_summary_rows(rows)
    assert summary[0]["top_label"] == "Fibroblast"
    assert summary[0]["confidence_bucket"] == "medium"


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
    assert "celltypist_model" in spec_text


def main() -> int:
    test_species_normalization()
    test_model_selection_prefers_matching_tissue_and_species()
    test_model_selection_prefers_cross_species_heart_over_generic_mouse()
    test_model_selection_uses_explicit_model()
    test_resolve_input_h5ad_prefers_scrna_prep()
    test_cluster_summary()
    test_software_versions_contract()
    print("scrna_annotate_celltypist tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
