#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMPLATE_DIR.parents[1]


def load_run_module():
    sys.path.insert(0, str(TEMPLATE_DIR))
    spec = importlib.util.spec_from_file_location("scrna_annotate_audit_run", TEMPLATE_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_function_module(name: str):
    path = REPO_ROOT / "functions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeBindingContext:
    def __init__(self, outputs: dict[tuple[str, str], str]):
        self.outputs = outputs
        self.project = SimpleNamespace(data={"templates": []})

    def latest_output(self, key: str, *, template_id: str):
        return self.outputs.get((template_id, key), "")


def test_label_normalization_with_aliases() -> None:
    run = load_run_module()
    aliases = {
        run.canonical_key("CD4+ T cells"): {"normalized_label": "CD4 T cell", "broad_label": "T/NK cell"},
    }
    assert run.normalize_label("CD4+ T cells", aliases)["normalized_label"] == "CD4 T cell"
    assert run.normalize_label("Macrophages", {})["broad_label"] == "Myeloid"


def test_agreement_levels() -> None:
    run = load_run_module()
    records = {
        "celltypist": {"label": "CD4 T cell", "normalized_label": "CD4 T cell", "broad_label": "T/NK cell", "confidence": "high"},
        "scanvi_reference": {"label": "T helper cell", "normalized_label": "CD4 T cell", "broad_label": "T/NK cell", "confidence": "medium"},
    }
    assert run.agreement_level(records) == "full_agreement"
    records["sctype"] = {"label": "CD8 T cell", "normalized_label": "CD8 T cell", "broad_label": "T/NK cell", "confidence": "medium"}
    assert run.agreement_level(records) == "lineage_agreement"
    records["manual_markers"] = {"label": "Macrophage", "normalized_label": "Macrophage", "broad_label": "Myeloid", "confidence": "high"}
    assert run.agreement_level(records) == "method_conflict"


def test_suggested_label_weights_marker_evidence() -> None:
    run = load_run_module()
    records = {
        "celltypist": {"label": "B cell", "normalized_label": "B cell", "broad_label": "B cell", "confidence": "medium", "score": 0.6},
        "manual_markers": {"label": "Plasma cell", "normalized_label": "Plasma cell", "broad_label": "B cell", "confidence": "high", "score": 0.9},
    }
    assert run.suggested_label(records, {})["label"] == "Plasma cell"


def test_apply_final_decisions_prefers_user_table() -> None:
    run = load_run_module()
    draft_rows = [
        {
            "cluster_id": "0",
            "suggested_label": "T cell",
            "suggested_broad_label": "T/NK cell",
            "decision": "Needs review",
            "confidence": "medium",
            "agreement_level": "lineage_agreement",
            "review_priority": "medium",
            "review_status": "not_reviewed",
            "final_label": "",
            "reviewer_note": "",
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        table = Path(tmp) / "final_annotation_decisions.csv"
        table.write_text(
            "cluster_id,suggested_label,suggested_broad_label,decision,confidence,agreement_level,review_priority,review_status,final_label,reviewer_note\n"
            "0,T cell,T/NK cell,Needs review,medium,lineage_agreement,medium,changed,CD4 T cell,manual choice\n",
            encoding="utf-8",
        )
        rows, source, warnings = run.apply_final_decisions(draft_rows, table, {})
    assert source == "user_final_decisions"
    assert not warnings
    assert rows[0]["final_label"] == "CD4 T cell"
    assert rows[0]["review_status"] == "changed"


def test_attach_final_decisions_tracks_bulk_fill_source() -> None:
    run = load_run_module()
    cards = [
        {
            "cluster_id": "0",
            "suggested_label": "T cell",
            "final": {},
        }
    ]
    final_by_cluster = {
        "0": {
            "cluster_id": "0",
            "final_label": "CD4 T cell",
            "review_status": "bulk_filled",
            "reviewer_note": "Bulk-filled from CellTypist",
        }
    }
    output = run.attach_final_decisions(cards, final_by_cluster, "user_final_decisions")
    assert output[0]["final"]["label"] == "CD4 T cell"
    assert output[0]["final"]["review_status"] == "bulk_filled"
    assert output[0]["final"]["label_source"] == "bulk_fill"


def test_normalize_umap_specs() -> None:
    run = load_run_module()
    specs = run.normalize_umap_specs(
        [
            {
                "key": "X umap nn15 md0.5",
                "n_neighbors": 15,
                "min_dist": 0.5,
                "spread": 1.0,
                "explanation": "balanced",
            }
        ]
    )
    assert specs[0]["key"] == "X_umap_nn15_md0_5"
    assert specs[0]["n_neighbors"] == 15
    assert specs[0]["explanation"] == "balanced"


def test_write_final_h5ad_copies_selected_generated_umap() -> None:
    run = load_run_module()
    try:
        import anndata as ad
        import numpy as np
        import pandas as pd
    except ImportError:
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_h5ad = tmp_path / "input.h5ad"
        output_h5ad = tmp_path / "output.h5ad"
        generated_npz = tmp_path / "umap_candidates.npz"
        adata = ad.AnnData(
            X=np.ones((3, 2)),
            obs=pd.DataFrame({"leiden": ["0", "1", "1"]}, index=["a", "b", "c"]),
        )
        adata.obsm["X_umap"] = np.zeros((3, 2), dtype="float32")
        adata.write_h5ad(input_h5ad)
        np.savez_compressed(generated_npz, X_umap_candidate=np.array([[0, 0], [2, 2], [3, 3]], dtype="float32"))
        old_npz = run.UMAP_CANDIDATES_NPZ
        run.UMAP_CANDIDATES_NPZ = generated_npz
        try:
            run.write_final_h5ad(
                input_h5ad,
                output_h5ad,
                "leiden",
                [
                    {"cluster_id": "0", "suggested_label": "A", "agreement_level": "full_agreement", "confidence": "high", "final": {"label": "A", "review_status": "accepted", "label_source": "reviewed"}},
                    {"cluster_id": "1", "suggested_label": "B", "agreement_level": "full_agreement", "confidence": "high", "final": {"label": "B", "review_status": "bulk_filled", "label_source": "bulk_fill"}},
                ],
                {"selected_umap_key": "X_umap_candidate", "selected_umap_reason": "best visual balance"},
                [],
            )
        finally:
            run.UMAP_CANDIDATES_NPZ = old_npz
        final = ad.read_h5ad(output_h5ad)
    assert "X_umap_candidate" in final.obsm
    assert np.array_equal(final.obsm["X_umap"], final.obsm["X_umap_candidate"])
    assert final.uns["scrna_annotate_audit"]["selected_umap_key"] == "X_umap_candidate"


def test_build_annotation_cards() -> None:
    run = load_run_module()
    records = {
        "1": {
            "celltypist": {"label": "Monocytes", "normalized_label": "Monocyte", "broad_label": "Myeloid", "confidence": "high", "score": 0.9, "candidates": []},
            "sctype": {"label": "Macrophages", "normalized_label": "Macrophage", "broad_label": "Myeloid", "confidence": "medium", "score": 0.5, "candidates": []},
        }
    }
    cards = run.build_annotation_cards({"1": 42}, records, {}, ["celltypist", "sctype"])
    assert cards[0]["agreement_level"] == "lineage_agreement"
    assert cards[0]["review_priority"] == "medium"


def test_list_available_annotation_results() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        keep = project / "scrna_annotate_celltypist" / "results" / "annotation_result.json"
        skip = project / "scrna_annotate_audit" / "results" / "annotation_result.json"
        unrelated = project / "scrna_prep" / "results" / "annotation_result.json"
        keep.parent.mkdir(parents=True)
        skip.parent.mkdir(parents=True)
        unrelated.parent.mkdir(parents=True)
        keep.write_text("{}", encoding="utf-8")
        skip.write_text("{}", encoding="utf-8")
        unrelated.write_text("{}", encoding="utf-8")
        paths = run.list_available_annotation_results(project)
    assert paths == [keep]


def test_provider_identity_preserves_source_directory() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        result = project / "scrna_annotate_gse230531" / "results" / "annotation_result.json"
        result.parent.mkdir(parents=True)
        result.write_text(
            '{"template":{"name":"scrna_annotate_manual_markers"},"cluster_predictions":[]}',
            encoding="utf-8",
        )
        provider = run.load_provider_result(result, [])
    assert provider["method_id"] == "gse230531"
    assert provider["method_family"] == "manual_markers"
    assert provider["source_template"] == "scrna_annotate_gse230531"


def test_provider_identity_accepts_legacy_template_string() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        result = project / "scrna_annotate_sctype" / "results" / "annotation_result.json"
        result.parent.mkdir(parents=True)
        result.write_text('{"template":"scrna_annotate_sctype","cluster_predictions":[]}', encoding="utf-8")
        provider = run.load_provider_result(result, [])
    assert provider["template_name"] == "scrna_annotate_sctype"
    assert provider["method_family"] == "sctype"


def test_software_versions_contract() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "software_versions:" in template_text
    assert "path: results/software_versions.json" in template_text
    assert "path: results/audit_report_static.html" in template_text
    assert "path: results/audit_report_static.qmd" in template_text
    assert 'python3 "${pack_root}/functions/software_versions.py"' in run_sh_text
    assert '--spec "${script_dir}/software_versions_spec.yaml"' in run_sh_text
    assert 'linkar collect "${script_dir}"' in run_sh_text
    assert 'linkar clean "${script_dir}" --yes' in run_sh_text
    assert "cleanup_runtime()" in run_sh_text
    assert "audit_report_static.html" in run_sh_text
    assert "final_decisions" in spec_text


def test_default_pack_binding_uses_audit_specific_resolvers() -> None:
    pack_text = (REPO_ROOT / "linkar_pack.yaml").read_text(encoding="utf-8")
    assert "scrna_annotate_audit:" in pack_text
    assert "function: get_scrna_annotate_audit_input_h5ad" in pack_text
    assert "function: get_scrna_annotate_audit_input_source_template" in pack_text


def test_audit_binding_prefers_integrated_h5ad() -> None:
    h5ad = load_function_module("get_scrna_annotate_audit_input_h5ad")
    source = load_function_module("get_scrna_annotate_audit_input_source_template")
    ctx = FakeBindingContext(
        {
            ("scrna_prep", "scrna_prep_h5ad"): "/project/scrna_prep/adata.prep.h5ad",
            ("scrna_integrate", "integrated_h5ad"): "/project/scrna_integrate/results/adata.integrated.h5ad",
        }
    )
    assert h5ad.resolve(ctx) == "/project/scrna_integrate/results/adata.integrated.h5ad"
    assert source.resolve(ctx) == "scrna_integrate"


def test_audit_binding_falls_back_to_prep_h5ad() -> None:
    h5ad = load_function_module("get_scrna_annotate_audit_input_h5ad")
    source = load_function_module("get_scrna_annotate_audit_input_source_template")
    ctx = FakeBindingContext({("scrna_prep", "scrna_prep_h5ad"): "/project/scrna_prep/adata.prep.h5ad"})
    assert h5ad.resolve(ctx) == "/project/scrna_prep/adata.prep.h5ad"
    assert source.resolve(ctx) == "scrna_prep"


def main() -> int:
    test_label_normalization_with_aliases()
    test_agreement_levels()
    test_suggested_label_weights_marker_evidence()
    test_apply_final_decisions_prefers_user_table()
    test_attach_final_decisions_tracks_bulk_fill_source()
    test_normalize_umap_specs()
    test_write_final_h5ad_copies_selected_generated_umap()
    test_build_annotation_cards()
    test_list_available_annotation_results()
    test_provider_identity_preserves_source_directory()
    test_provider_identity_accepts_legacy_template_string()
    test_software_versions_contract()
    test_default_pack_binding_uses_audit_specific_resolvers()
    test_audit_binding_prefers_integrated_h5ad()
    test_audit_binding_falls_back_to_prep_h5ad()
    print("scrna_annotate_audit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
