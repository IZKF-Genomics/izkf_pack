#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


def load_run_module():
    sys.path.insert(0, str(TEMPLATE_DIR))
    spec = importlib.util.spec_from_file_location("scrna_annotate_audit_run", TEMPLATE_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
            "final_broad_label": "",
            "reviewer_note": "",
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        table = Path(tmp) / "final_annotation_decisions.csv"
        table.write_text(
            "cluster_id,suggested_label,suggested_broad_label,decision,confidence,agreement_level,review_priority,review_status,final_label,final_broad_label,reviewer_note\n"
            "0,T cell,T/NK cell,Needs review,medium,lineage_agreement,medium,changed,CD4 T cell,T/NK cell,manual choice\n",
            encoding="utf-8",
        )
        rows, source, warnings = run.apply_final_decisions(draft_rows, table, {})
    assert source == "user_final_decisions"
    assert not warnings
    assert rows[0]["final_label"] == "CD4 T cell"
    assert rows[0]["review_status"] == "changed"


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


def test_software_versions_contract() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "software_versions:" in template_text
    assert "path: results/software_versions.json" in template_text
    assert 'python3 "${pack_root}/functions/software_versions.py"' in run_sh_text
    assert '--spec "${script_dir}/software_versions_spec.yaml"' in run_sh_text
    assert 'linkar collect "${script_dir}"' in run_sh_text
    assert 'linkar clean "${script_dir}" --yes' in run_sh_text
    assert "cleanup_runtime()" in run_sh_text
    assert "final_decisions" in spec_text


def main() -> int:
    test_label_normalization_with_aliases()
    test_agreement_levels()
    test_suggested_label_weights_marker_evidence()
    test_apply_final_decisions_prefers_user_table()
    test_build_annotation_cards()
    test_list_available_annotation_results()
    test_provider_identity_preserves_source_directory()
    test_software_versions_contract()
    print("scrna_annotate_audit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
