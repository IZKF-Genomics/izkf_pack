#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tomllib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = Path(os.environ.get("LINKAR_PROJECT_DIR", TEMPLATE_DIR.parent)).resolve()
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
TABLES_DIR = RESULTS_DIR / "tables"
CONFIG_DIR = TEMPLATE_DIR / "config"
SCHEMA_VERSION = "izkf_annotation_audit.v1"
TEMPLATE_NAME = "scrna_annotate_audit"
FINAL_H5AD = RESULTS_DIR / "adata.final_annotated.h5ad"

METHOD_FAMILIES = {
    "scrna_annotate_celltypist": "celltypist",
    "scrna_annotate_manual_markers": "manual_markers",
    "scrna_annotate_sctype": "sctype",
    "scrna_annotate_scanvi_reference": "scanvi_reference",
}
DEFAULT_PROVIDER_ORDER = ["celltypist", "manual_markers", "sctype", "scanvi_reference"]
NO_LABELS = {
    "",
    "unknown",
    "unassigned",
    "nan",
    "none",
    "no match",
    "no manual marker match",
    "no manual marker-supported candidate",
    "no sctype match",
    "no catalog-supported candidate",
}

BASE_COMPARISON_FIELDS = [
    "cluster_id",
    "n_cells",
    "suggested_label",
    "suggested_broad_label",
    "decision",
    "confidence",
    "agreement_level",
    "review_priority",
]
CANDIDATE_FIELDS = [
    "cluster_id",
    "method_id",
    "rank",
    "label",
    "normalized_label",
    "broad_label",
    "score",
    "score_name",
    "confidence",
    "evidence",
]
DECISION_FIELDS = [
    "cluster_id",
    "suggested_label",
    "suggested_broad_label",
    "decision",
    "confidence",
    "agreement_level",
    "review_priority",
    "review_status",
    "final_label",
    "final_broad_label",
    "reviewer_note",
]
MARKER_FIELDS = ["cluster_id", "gene", "mean_expression", "pct_expressing", "source"]
CLUSTER_MARKER_FIELDS = [
    "cluster_id",
    "rank",
    "gene",
    "score",
    "log2_fold_change",
    "mean_expression",
    "mean_other",
    "pct_expressing",
    "pct_other",
    "source",
]


def progress(message: str) -> None:
    print(f"[{TEMPLATE_NAME}] {message}", flush=True)


def main() -> int:
    started_at = utc_now()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    params = load_params()
    warnings: list[str] = []

    aliases = load_label_aliases(resolve_path(params["label_aliases"], base=TEMPLATE_DIR))
    result_paths = discover_annotation_results(params)
    providers = [load_provider_result(path, warnings) for path in result_paths]
    providers = [provider for provider in providers if provider]
    providers = uniquify_provider_ids(providers)
    provider_order = provider_order_from_providers(providers)
    if not providers:
        warnings.append("No annotation_result.json files were found for the configured annotation templates.")

    input_h5ad = resolve_input_h5ad(params, providers, warnings)
    cluster_sizes = load_cluster_sizes(input_h5ad, params["cluster_key"], providers, warnings)
    provider_records = provider_records_by_cluster(providers, aliases, params, warnings)
    cards = build_annotation_cards(cluster_sizes, provider_records, aliases, provider_order)
    comparison_rows = comparison_rows_from_cards(cards)
    candidate_rows = candidate_rows_from_cards(cards)
    marker_rows = marker_expression_rows(input_h5ad, cards, params, warnings)
    cluster_marker_rows = cluster_marker_gene_rows(input_h5ad, params, warnings)
    draft_rows = decision_rows_from_cards(cards)
    final_decision_path = resolve_path(params["final_decisions"], base=TEMPLATE_DIR)
    final_rows, final_source, final_warnings = apply_final_decisions(draft_rows, final_decision_path, aliases)
    warnings.extend(final_warnings)
    final_by_cluster = {str(row["cluster_id"]): row for row in final_rows}
    final_cards = attach_final_decisions(cards, final_by_cluster, final_source)

    write_csv(TABLES_DIR / "annotation_method_comparison.csv", comparison_rows, comparison_fields(provider_order))
    write_csv(TABLES_DIR / "annotation_candidates_long.csv", candidate_rows, CANDIDATE_FIELDS)
    write_csv(TABLES_DIR / "final_annotation_decisions_draft.csv", draft_rows, DECISION_FIELDS)
    write_csv(TABLES_DIR / "final_annotation_decisions_applied.csv", final_rows, DECISION_FIELDS)
    write_csv(TABLES_DIR / "marker_expression_summary.csv", marker_rows, MARKER_FIELDS)
    write_csv(TABLES_DIR / "cluster_marker_genes.csv", cluster_marker_rows, CLUSTER_MARKER_FIELDS)
    write_json(RESULTS_DIR / "annotation_audit_cards.json", final_cards)

    artifacts: dict[str, Any] = {
        "report_html": "results/report.html",
        "report_qmd": "results/report.qmd",
        "annotation_cards": "results/annotation_audit_cards.json",
        "tables": [
            "results/tables/annotation_method_comparison.csv",
            "results/tables/annotation_candidates_long.csv",
            "results/tables/final_annotation_decisions_draft.csv",
            "results/tables/final_annotation_decisions_applied.csv",
            "results/tables/marker_expression_summary.csv",
            "results/tables/cluster_marker_genes.csv",
        ],
    }
    if bool_param(params["write_h5ad"]) and input_h5ad.exists():
        write_final_h5ad(input_h5ad, FINAL_H5AD, params["cluster_key"], final_cards)
        artifacts["final_h5ad"] = "results/adata.final_annotated.h5ad"
    elif bool_param(params["write_h5ad"]):
        warnings.append(f"Final h5ad was not written because input_h5ad was not found: {input_h5ad}")

    state = "completed_with_warnings" if warnings else "completed"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "template": {"name": TEMPLATE_NAME, "version": "0.1.0"},
        "run": {
            "state": state,
            "warnings": warnings,
            "errors": [],
            "started_at": started_at,
            "completed_at": utc_now(),
        },
        "input": {
            "h5ad": str(input_h5ad),
            "input_source_template": params.get("input_source_template") or None,
            "organism": params.get("organism") or None,
            "organism_id": params.get("organism_id") or None,
            "tissue": params.get("tissue") or None,
            "cluster_key": params["cluster_key"],
            "sample_key": params.get("sample_key") or None,
            "expression_layer": params["expression_layer"],
        },
        "method": {
            "name": "Cluster-level annotation audit",
            "annotation_level": "cluster",
            "parameters": {
                "annotation_templates": params["annotation_templates"],
                "providers": provider_order,
                "label_aliases": params["label_aliases"],
                "final_decisions": params["final_decisions"],
                "top_n_candidates": int(params["top_n_candidates"]),
            },
        },
        "methods": [
            {
                "step": "Provider result aggregation",
                "tool": "izkf annotation_result.json audit",
                "parameters": {"providers": provider_order},
            },
            {
                "step": "Human review table application",
                "tool": "CSV final annotation decision mapping",
                "parameters": {"decision_source": final_source},
                "interpretation": "Final labels are taken from the user decision table when present; otherwise conservative suggested labels are written with label_source=draft.",
            },
        ],
        "resources": provider_resources(providers) + [
            {
                "role": "label_aliases",
                "path": str(resolve_path(params["label_aliases"], base=TEMPLATE_DIR)),
                "sha256": sha256_file(resolve_path(params["label_aliases"], base=TEMPLATE_DIR)),
            }
        ],
        "artifacts": artifacts,
    }
    copy_review_app()
    artifacts["review_app"] = "results/review_app.py"
    write_json(RESULTS_DIR / "annotation_audit.json", payload)
    render_report()
    payload["run"]["completed_at"] = utc_now()
    write_json(RESULTS_DIR / "annotation_audit.json", payload)
    progress(f"done: {RESULTS_DIR / 'report.html'}")
    return 0


def load_params() -> dict[str, Any]:
    config = read_toml(CONFIG_DIR / "dataset.toml")
    dataset = dict(config.get("dataset", {}))
    audit = dict(config.get("audit", {}))
    outputs = dict(config.get("outputs", {}))
    params = {
        "input_h5ad": dataset.get("input_h5ad", ""),
        "input_source_template": dataset.get("input_source_template", ""),
        "organism": dataset.get("organism", "mouse"),
        "organism_id": dataset.get("organism_id", ""),
        "tissue": dataset.get("tissue", ""),
        "cluster_key": dataset.get("cluster_key", "leiden"),
        "sample_key": dataset.get("sample_key", "sample_id"),
        "expression_layer": dataset.get("expression_layer", "X"),
        "annotation_templates": audit.get("annotation_templates", list(METHOD_FAMILIES)),
        "annotation_result_paths": audit.get("annotation_result_paths", []),
        "label_aliases": audit.get("label_aliases", "config/label_aliases.csv"),
        "final_decisions": audit.get("final_decisions", "config/final_annotation_decisions.csv"),
        "top_n_candidates": audit.get("top_n_candidates", 5),
        "marker_expression_max_genes": audit.get("marker_expression_max_genes", 60),
        "cluster_marker_top_n": audit.get("cluster_marker_top_n", 200),
        "cluster_marker_min_pct": audit.get("cluster_marker_min_pct", 10),
        "write_h5ad": outputs.get("write_h5ad", True),
    }
    env_map = {
        "input_h5ad": "INPUT_H5AD",
        "organism": "ORGANISM",
        "tissue": "TISSUE",
        "cluster_key": "CLUSTER_KEY",
        "sample_key": "SAMPLE_ID_KEY",
        "expression_layer": "EXPRESSION_LAYER",
        "write_h5ad": "WRITE_H5AD",
    }
    for key, env_name in env_map.items():
        value = os.environ.get(env_name)
        if value is not None and value != "":
            params[key] = value
    params["annotation_templates"] = [str(item) for item in params["annotation_templates"]]
    return params


def discover_annotation_results(params: dict[str, Any]) -> list[Path]:
    configured = params.get("annotation_result_paths") or []
    paths = [resolve_path(path, base=PROJECT_DIR) for path in configured]
    for template_id in params["annotation_templates"]:
        paths.append(PROJECT_DIR / template_id / "results" / "annotation_result.json")
    paths.extend(list_available_annotation_results(PROJECT_DIR))
    seen: set[Path] = set()
    existing = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        existing.append(resolved)
    return existing


def list_available_annotation_results(project_dir: Path) -> list[Path]:
    """Return all sibling scrna annotation result JSON files available in a project.

    The audit template consumes provider outputs, so it deliberately excludes its own
    result JSON to avoid self-ingestion on reruns.
    """
    paths = []
    for path in sorted(project_dir.glob("scrna_annotate_*/results/annotation_result.json")):
        template_id = path.parents[1].name
        if template_id == TEMPLATE_NAME:
            continue
        paths.append(path)
    return paths


def load_provider_result(path: Path, warnings: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"Could not read provider result {path}: {exc}")
        return None
    source_template = path.parents[1].name
    template_name = str(payload.get("template", {}).get("name") or source_template)
    method_family = infer_method_family(template_name, source_template)
    method_id = provider_id_from_source(template_name, source_template)
    return {
        "method_id": method_id,
        "method_family": method_family,
        "display_name": display_name_from_provider_id(method_id),
        "template_name": template_name,
        "source_template": source_template,
        "path": path,
        "payload": payload,
    }


def infer_method_family(template_name: str, source_template: str) -> str:
    if template_name in METHOD_FAMILIES:
        return METHOD_FAMILIES[template_name]
    source = source_template.lower()
    if "celltypist" in source:
        return "celltypist"
    if "sctype" in source:
        return "sctype"
    if "scanvi" in source:
        return "scanvi_reference"
    if "manual" in source or "gse" in source:
        return "manual_markers"
    return provider_slug(source_template)


def provider_id_from_source(template_name: str, source_template: str) -> str:
    source_id = provider_slug(source_template)
    if source_template != template_name:
        return source_id
    return METHOD_FAMILIES.get(template_name, source_id)


def provider_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("scrna_annotate_"):
        text = text.replace("scrna_annotate_", "", 1)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "provider"


def display_name_from_provider_id(provider_id: str) -> str:
    labels = {
        "celltypist": "CellTypist",
        "manual_markers": "Manual markers",
        "sctype": "ScType",
        "scanvi_reference": "scANVI reference",
    }
    return labels.get(provider_id, provider_id.replace("_", " ").title())


def uniquify_provider_ids(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = defaultdict(int)
    output = []
    for provider in providers:
        updated = dict(provider)
        base = str(updated["method_id"])
        counts[base] += 1
        if counts[base] > 1:
            updated["method_id"] = f"{base}_{counts[base]}"
            updated["display_name"] = f"{updated.get('display_name') or display_name_from_provider_id(base)} {counts[base]}"
        output.append(updated)
    return output


def provider_order_from_providers(providers: list[dict[str, Any]]) -> list[str]:
    known = []
    extras = []
    for provider in providers:
        provider_id = str(provider["method_id"])
        if provider_id in DEFAULT_PROVIDER_ORDER:
            known.append(provider_id)
        else:
            extras.append(provider_id)
    ordered = [provider_id for provider_id in DEFAULT_PROVIDER_ORDER if provider_id in known]
    return ordered + sorted(extras)


def comparison_fields(provider_order: list[str]) -> list[str]:
    fields = list(BASE_COMPARISON_FIELDS)
    for provider_id in provider_order:
        fields.extend([f"{provider_id}_label", f"{provider_id}_confidence"])
    return fields


def resolve_input_h5ad(params: dict[str, Any], providers: list[dict[str, Any]], warnings: list[str]) -> Path:
    if params.get("input_h5ad"):
        return resolve_path(params["input_h5ad"], base=TEMPLATE_DIR)
    for provider in providers:
        h5ad = provider["payload"].get("input", {}).get("h5ad")
        if h5ad and Path(str(h5ad)).exists():
            params["input_source_template"] = provider["template_name"]
            return Path(str(h5ad)).expanduser().resolve()
    candidates = [
        PROJECT_DIR / "scrna_prep" / "results" / "adata.prep.h5ad",
        PROJECT_DIR / "scrna_integrate" / "results" / "adata.integrated.h5ad",
    ]
    for candidate in candidates:
        if candidate.exists():
            params["input_source_template"] = candidate.parent.parent.name
            return candidate.resolve()
    warnings.append("No input h5ad was configured or found in provider metadata.")
    return resolve_path(params.get("input_h5ad") or candidates[0], base=PROJECT_DIR)


def load_cluster_sizes(input_h5ad: Path, cluster_key: str, providers: list[dict[str, Any]], warnings: list[str]) -> dict[str, int]:
    if input_h5ad.exists():
        try:
            import anndata as ad

            adata = ad.read_h5ad(input_h5ad, backed="r")
            try:
                if cluster_key in adata.obs:
                    counts = adata.obs[cluster_key].astype(str).value_counts().to_dict()
                    return {str(key): int(value) for key, value in counts.items()}
                warnings.append(f"cluster_key '{cluster_key}' was not found in input h5ad.")
            finally:
                try:
                    adata.file.close()
                except Exception:
                    pass
        except Exception as exc:
            warnings.append(f"Could not read cluster sizes from {input_h5ad}: {exc}")
    sizes: dict[str, int] = {}
    for provider in providers:
        for prediction in provider["payload"].get("cluster_predictions") or []:
            cluster_id = str(prediction.get("cluster_id", ""))
            if cluster_id:
                sizes[cluster_id] = max(sizes.get(cluster_id, 0), int_or_zero(prediction.get("n_cells")))
    return sizes


def provider_records_by_cluster(
    providers: list[dict[str, Any]],
    aliases: dict[str, dict[str, str]],
    params: dict[str, Any],
    warnings: list[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    by_cluster: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    top_n = int(params["top_n_candidates"])
    for provider in providers:
        method_id = provider["method_id"]
        method_family = provider.get("method_family") or method_id
        payload = provider["payload"]
        cluster_predictions = payload.get("cluster_predictions") or []
        if not cluster_predictions:
            warnings.append(f"{method_id} has no cluster_predictions in annotation_result.json.")
        for prediction in cluster_predictions:
            cluster_id = str(prediction.get("cluster_id", ""))
            if not cluster_id:
                continue
            label = clean_label(prediction.get("top_label"))
            confidence = clean_label(prediction.get("confidence_bucket")) or clean_label(prediction.get("confidence")) or "unknown"
            candidates = normalize_candidates(prediction.get("candidates") or [], aliases, top_n)
            if not candidates and informative_label(label):
                normalized = normalize_label(label, aliases)
                candidates = [
                    {
                        "rank": 1,
                        "label": label,
                        "normalized_label": normalized["normalized_label"],
                        "broad_label": normalized["broad_label"],
                        "score": score_from_prediction(prediction),
                        "score_name": score_name_from_prediction(prediction),
                        "confidence": confidence,
                        "evidence": "",
                    }
                ]
            normalized_top = normalize_label(label, aliases)
            by_cluster[cluster_id][method_id] = {
                "method_id": method_id,
                "method_family": method_family,
                "display_name": provider.get("display_name") or method_id,
                "template_name": provider.get("template_name") or "",
                "source_template": provider.get("source_template") or "",
                "label": label,
                "normalized_label": normalized_top["normalized_label"],
                "broad_label": normalized_top["broad_label"],
                "confidence": confidence,
                "review_status": clean_label(prediction.get("review_status")),
                "score": score_from_prediction(prediction),
                "score_name": score_name_from_prediction(prediction),
                "candidates": candidates,
            }
    return by_cluster


def normalize_candidates(candidates: list[Any], aliases: dict[str, dict[str, str]], top_n: int) -> list[dict[str, Any]]:
    rows = []
    for index, candidate in enumerate(candidates[:top_n], start=1):
        if not isinstance(candidate, dict):
            continue
        label = clean_label(candidate.get("label_raw") or candidate.get("label") or candidate.get("top_label"))
        if not informative_label(label):
            continue
        normalized = normalize_label(label, aliases)
        evidence_items = candidate.get("evidence_items") or candidate.get("evidence") or []
        rows.append(
            {
                "rank": int(candidate.get("rank") or index),
                "label": label,
                "normalized_label": normalized["normalized_label"],
                "broad_label": normalized["broad_label"],
                "score": float_or_blank(candidate.get("provider_score") or candidate.get("score") or candidate.get("probability")),
                "score_name": clean_label(candidate.get("provider_score_name") or candidate.get("score_name")),
                "confidence": clean_label(candidate.get("confidence_bucket") or candidate.get("confidence")),
                "evidence": compact_evidence(evidence_items),
            }
        )
    return rows


def build_annotation_cards(
    cluster_sizes: dict[str, int],
    provider_records: dict[str, dict[str, dict[str, Any]]],
    aliases: dict[str, dict[str, str]],
    provider_order: list[str],
) -> list[dict[str, Any]]:
    cluster_ids = sorted(set(cluster_sizes) | set(provider_records), key=cluster_sort_key)
    cards = []
    for cluster_id in cluster_ids:
        records = provider_records.get(cluster_id, {})
        suggested = suggested_label(records, aliases)
        agreement = agreement_level(records)
        confidence = overall_confidence(records, agreement)
        decision = decision_from_agreement(agreement, confidence, records)
        review_priority = review_priority_from_decision(decision, agreement, confidence, records)
        methods = {method: records.get(method, empty_method(method)) for method in provider_order}
        for method, record in records.items():
            if method not in methods:
                methods[method] = record
        cards.append(
            {
                "cluster_id": cluster_id,
                "n_cells": int(cluster_sizes.get(cluster_id, 0)),
                "suggested_label": suggested["label"],
                "suggested_broad_label": suggested["broad_label"],
                "decision": decision,
                "confidence": confidence,
                "agreement_level": agreement,
                "review_priority": review_priority,
                "methods": methods,
                "reasoning": reasoning_from_records(records, agreement),
                "final": {},
            }
        )
    return cards


def suggested_label(records: dict[str, dict[str, Any]], aliases: dict[str, dict[str, str]]) -> dict[str, str]:
    scores: dict[str, float] = defaultdict(float)
    labels_by_norm: dict[str, list[str]] = defaultdict(list)
    broad_by_norm: dict[str, str] = {}
    for method_id, record in records.items():
        label = record.get("label", "")
        if not informative_label(label):
            continue
        normalized = record.get("normalized_label") or normalize_label(label, aliases)["normalized_label"]
        broad = record.get("broad_label") or normalize_label(label, aliases)["broad_label"]
        family = record.get("method_family") or method_id
        weight = 1.2 if family in {"manual_markers", "sctype"} else 1.0
        weight *= confidence_weight(record.get("confidence"))
        score = record.get("score")
        if isinstance(score, (int, float)) and not math.isnan(float(score)):
            weight += min(max(float(score), 0.0), 1.0) * 0.2
        scores[normalized] += weight
        labels_by_norm[normalized].append(label)
        broad_by_norm[normalized] = broad
    if not scores:
        return {"label": "Unknown", "normalized_label": "unknown", "broad_label": "Unknown"}
    best_norm = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
    label = Counter(labels_by_norm[best_norm]).most_common(1)[0][0]
    return {"label": label, "normalized_label": best_norm, "broad_label": broad_by_norm.get(best_norm) or label}


def agreement_level(records: dict[str, dict[str, Any]]) -> str:
    informative = [record for record in records.values() if informative_label(record.get("label"))]
    if len(informative) < 2:
        return "insufficient_evidence"
    normalized = {record.get("normalized_label") for record in informative if record.get("normalized_label")}
    if len(normalized) == 1:
        return "full_agreement"
    broad = {record.get("broad_label") for record in informative if record.get("broad_label")}
    if len(broad) == 1:
        return "lineage_agreement"
    return "method_conflict"


def overall_confidence(records: dict[str, dict[str, Any]], agreement: str) -> str:
    values = [confidence_weight(record.get("confidence")) for record in records.values() if informative_label(record.get("label"))]
    if not values:
        return "unknown"
    mean = sum(values) / len(values)
    if agreement == "method_conflict":
        mean -= 0.7
    if agreement == "full_agreement":
        mean += 0.3
    if mean >= 2.5:
        return "high"
    if mean >= 1.5:
        return "medium"
    return "low"


def decision_from_agreement(agreement: str, confidence: str, records: dict[str, dict[str, Any]]) -> str:
    if agreement == "full_agreement" and confidence in {"high", "medium"}:
        return "Accepted"
    if agreement == "method_conflict":
        return "Ambiguous"
    if not records:
        return "Unknown"
    return "Needs review"


def review_priority_from_decision(decision: str, agreement: str, confidence: str, records: dict[str, dict[str, Any]]) -> str:
    if decision == "Ambiguous" or agreement == "method_conflict":
        return "high"
    if confidence in {"low", "unknown"}:
        return "high"
    if agreement in {"lineage_agreement", "insufficient_evidence"}:
        return "medium"
    return "low"


def reasoning_from_records(records: dict[str, dict[str, Any]], agreement: str) -> dict[str, list[str]]:
    labels = [f"{method}: {record.get('label')}" for method, record in records.items() if informative_label(record.get("label"))]
    supports = []
    contradictions = []
    uncertainties = []
    if agreement == "full_agreement" and labels:
        supports.append("Annotation providers agree after label normalization.")
    elif agreement == "lineage_agreement":
        supports.append("Providers agree at broad lineage level but differ in subtype granularity.")
        uncertainties.append("Subtype-level naming should be reviewed manually.")
    elif agreement == "method_conflict":
        contradictions.append("Providers assign conflicting broad lineages.")
    else:
        uncertainties.append("Fewer than two informative provider labels were available.")
    if labels:
        supports.append("; ".join(labels))
    return {"supports": supports, "contradictions": contradictions, "uncertainties": uncertainties}


def comparison_rows_from_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for card in cards:
        row = {field: "" for field in BASE_COMPARISON_FIELDS}
        for field in ["cluster_id", "n_cells", "suggested_label", "suggested_broad_label", "decision", "confidence", "agreement_level", "review_priority"]:
            row[field] = card.get(field, "")
        for method in card.get("methods", {}):
            record = card["methods"].get(method, {})
            row[f"{method}_label"] = record.get("label", "")
            row[f"{method}_confidence"] = record.get("confidence", "")
        rows.append(row)
    return rows


def candidate_rows_from_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for card in cards:
        for method in card.get("methods", {}):
            record = card["methods"].get(method, {})
            for candidate in record.get("candidates") or []:
                rows.append(
                    {
                        "cluster_id": card["cluster_id"],
                        "method_id": method,
                        **{field: candidate.get(field, "") for field in CANDIDATE_FIELDS if field not in {"cluster_id", "method_id"}},
                    }
                )
    return rows


def decision_rows_from_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "cluster_id": card["cluster_id"],
            "suggested_label": card["suggested_label"],
            "suggested_broad_label": card["suggested_broad_label"],
            "decision": card["decision"],
            "confidence": card["confidence"],
            "agreement_level": card["agreement_level"],
            "review_priority": card["review_priority"],
            "review_status": "accepted" if card["decision"] == "Accepted" and card["confidence"] == "high" else "not_reviewed",
            "final_label": card["suggested_label"] if card["decision"] == "Accepted" and card["confidence"] == "high" else "",
            "final_broad_label": card["suggested_broad_label"] if card["decision"] == "Accepted" and card["confidence"] == "high" else "",
            "reviewer_note": "",
        }
        for card in cards
    ]


def apply_final_decisions(
    draft_rows: list[dict[str, Any]],
    final_decision_path: Path,
    aliases: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], str, list[str]]:
    warnings: list[str] = []
    if final_decision_path.exists():
        rows = read_csv_dicts(final_decision_path)
        source = "user_final_decisions"
    else:
        rows = draft_rows
        source = "draft_suggestions"
        warnings.append(f"Final decision table not found: {final_decision_path}. Draft suggestions were applied with label_source=draft.")
    by_cluster = {str(row.get("cluster_id", "")).strip(): row for row in rows if str(row.get("cluster_id", "")).strip()}
    final_rows = []
    for draft in draft_rows:
        cluster_id = str(draft["cluster_id"])
        row = by_cluster.get(cluster_id, draft)
        review_status = clean_label(row.get("review_status")) or "not_reviewed"
        final_label = clean_label(row.get("final_label"))
        if not final_label and review_status in {"accepted", "changed"}:
            final_label = clean_label(row.get("reviewed_label"))
        if not final_label:
            final_label = clean_label(draft.get("suggested_label")) or "Unknown"
        final_broad = clean_label(row.get("final_broad_label"))
        if not final_broad:
            final_broad = normalize_label(final_label, aliases)["broad_label"]
        applied = dict(draft)
        applied["review_status"] = review_status
        applied["final_label"] = final_label
        applied["final_broad_label"] = final_broad
        applied["reviewer_note"] = clean_label(row.get("reviewer_note"))
        final_rows.append(applied)
        if review_status in {"accepted", "changed"} and final_label in {"", "Unknown"}:
            warnings.append(f"Cluster {cluster_id} is {review_status}, but final_label is empty or Unknown.")
    return final_rows, source, warnings


def attach_final_decisions(cards: list[dict[str, Any]], final_by_cluster: dict[str, dict[str, Any]], source: str) -> list[dict[str, Any]]:
    output = []
    for card in cards:
        updated = json.loads(json.dumps(card))
        row = final_by_cluster.get(str(card["cluster_id"]), {})
        label_source = "reviewed" if source == "user_final_decisions" and row.get("review_status") in {"accepted", "changed"} else "draft"
        if source == "user_final_decisions" and row.get("review_status") not in {"accepted", "changed"}:
            label_source = "user_table_fallback"
        updated["final"] = {
            "label": row.get("final_label") or card.get("suggested_label") or "Unknown",
            "broad_label": row.get("final_broad_label") or card.get("suggested_broad_label") or "Unknown",
            "review_status": row.get("review_status") or "not_reviewed",
            "reviewer_note": row.get("reviewer_note") or "",
            "label_source": label_source,
            "decision_source": source,
        }
        output.append(updated)
    return output


def marker_expression_rows(input_h5ad: Path, cards: list[dict[str, Any]], params: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    if not input_h5ad.exists():
        return []
    genes = selected_marker_genes(cards, int(params["marker_expression_max_genes"]))
    if not genes:
        return []
    try:
        import anndata as ad
        import numpy as np
        from scipy import sparse
    except Exception as exc:
        warnings.append(f"Marker expression summary skipped because dependencies are unavailable: {exc}")
        return []
    try:
        adata = ad.read_h5ad(input_h5ad)
    except Exception as exc:
        warnings.append(f"Could not read h5ad for marker expression summary: {exc}")
        return []
    cluster_key = params["cluster_key"]
    if cluster_key not in adata.obs:
        warnings.append(f"Marker expression summary skipped because cluster_key '{cluster_key}' is missing.")
        return []
    lookup = {str(gene).lower(): str(gene) for gene in adata.var_names}
    present = []
    for gene in genes:
        exact = gene if gene in adata.var_names else lookup.get(gene.lower())
        if exact and exact not in present:
            present.append(exact)
    if not present:
        return []
    layer = params["expression_layer"]
    view = adata[:, present]
    matrix = view.layers[layer] if layer and layer != "X" and layer in view.layers else view.X
    matrix = matrix.toarray() if sparse.issparse(matrix) else np.asarray(matrix)
    clusters = adata.obs[cluster_key].astype(str).values
    rows = []
    for cluster_id in sorted(set(clusters), key=cluster_sort_key):
        mask = clusters == cluster_id
        values = matrix[mask, :]
        for index, gene in enumerate(present):
            gene_values = values[:, index]
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "gene": gene,
                    "mean_expression": round(float(np.nanmean(gene_values)), 6),
                    "pct_expressing": round(float(np.nanmean(gene_values > 0) * 100), 3),
                    "source": "candidate_marker_evidence",
                }
            )
    return rows


def cluster_marker_gene_rows(input_h5ad: Path, params: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    if not input_h5ad.exists():
        return []
    try:
        import anndata as ad
        import numpy as np
        from scipy import sparse
    except Exception as exc:
        warnings.append(f"Cluster marker gene summary skipped because dependencies are unavailable: {exc}")
        return []
    try:
        adata = ad.read_h5ad(input_h5ad)
    except Exception as exc:
        warnings.append(f"Could not read h5ad for cluster marker gene summary: {exc}")
        return []
    cluster_key = params["cluster_key"]
    if cluster_key not in adata.obs:
        warnings.append(f"Cluster marker gene summary skipped because cluster_key '{cluster_key}' is missing.")
        return []
    layer = params["expression_layer"]
    matrix = adata.layers[layer] if layer and layer != "X" and layer in adata.layers else adata.X
    clusters = adata.obs[cluster_key].astype(str).values
    n_total = int(matrix.shape[0])
    if n_total == 0 or matrix.shape[1] == 0:
        return []
    top_n = max(1, int(params.get("cluster_marker_top_n", 200)))
    min_pct = max(0.0, float(params.get("cluster_marker_min_pct", 10)))
    if sparse.issparse(matrix):
        matrix = matrix.tocsr()
        total_sum = np.asarray(matrix.sum(axis=0)).ravel().astype(float)
        total_nnz = np.asarray(matrix.getnnz(axis=0)).ravel().astype(float)
    else:
        matrix = np.asarray(matrix)
        total_sum = np.asarray(np.nansum(matrix, axis=0)).ravel().astype(float)
        total_nnz = np.asarray(np.sum(matrix > 0, axis=0)).ravel().astype(float)
    genes = np.asarray([str(gene) for gene in adata.var_names])
    rows: list[dict[str, Any]] = []
    for cluster_id in sorted(set(clusters), key=cluster_sort_key):
        mask = clusters == cluster_id
        n_in = int(np.sum(mask))
        n_out = n_total - n_in
        if n_in == 0 or n_out == 0:
            continue
        if sparse.issparse(matrix):
            selected = matrix[mask, :]
            cluster_sum = np.asarray(selected.sum(axis=0)).ravel().astype(float)
            cluster_nnz = np.asarray(selected.getnnz(axis=0)).ravel().astype(float)
        else:
            selected = matrix[mask, :]
            cluster_sum = np.asarray(np.nansum(selected, axis=0)).ravel().astype(float)
            cluster_nnz = np.asarray(np.sum(selected > 0, axis=0)).ravel().astype(float)
        mean_in = cluster_sum / n_in
        mean_out = (total_sum - cluster_sum) / n_out
        pct_in = cluster_nnz / n_in * 100.0
        pct_out = (total_nnz - cluster_nnz) / n_out * 100.0
        positive_mean_in = np.maximum(mean_in, 0)
        positive_mean_out = np.maximum(mean_out, 0)
        log2fc = np.log2((positive_mean_in + 1e-9) / (positive_mean_out + 1e-9))
        mean_diff = mean_in - mean_out
        pct_diff = pct_in - pct_out
        score = log2fc + np.log1p(np.maximum(mean_diff, 0)) + (pct_diff / 100.0)
        score = np.where((mean_in > 0) & (mean_diff > 0) & (pct_in >= min_pct), score, -np.inf)
        if not np.isfinite(score).any():
            continue
        top_indices = np.argsort(score)[::-1][:top_n]
        rank = 1
        for index in top_indices:
            if not np.isfinite(score[index]):
                continue
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "rank": rank,
                    "gene": genes[index],
                    "score": round(float(score[index]), 6),
                    "log2_fold_change": round(float(log2fc[index]), 6),
                    "mean_expression": round(float(mean_in[index]), 6),
                    "mean_other": round(float(mean_out[index]), 6),
                    "pct_expressing": round(float(pct_in[index]), 3),
                    "pct_other": round(float(pct_out[index]), 3),
                    "source": "cluster_vs_rest_expression",
                }
            )
            rank += 1
    return rows


def selected_marker_genes(cards: list[dict[str, Any]], max_genes: int) -> list[str]:
    genes: list[str] = []
    for card in cards:
        for method in card.get("methods", {}):
            for candidate in card["methods"].get(method, {}).get("candidates") or []:
                evidence = str(candidate.get("evidence") or "")
                genes.extend(re.findall(r"\b[A-Za-z][A-Za-z0-9.-]{1,15}\b", evidence))
    ignored = {"score", "matched", "missing", "positive", "negative", "genes", "primary", "marker", "support"}
    ordered = []
    seen = set()
    for gene in genes:
        if gene.lower() in ignored or gene in seen:
            continue
        seen.add(gene)
        ordered.append(gene)
        if len(ordered) >= max_genes:
            break
    return ordered


def write_final_h5ad(input_h5ad: Path, output_h5ad: Path, cluster_key: str, cards: list[dict[str, Any]]) -> None:
    import anndata as ad
    import pandas as pd

    adata = ad.read_h5ad(input_h5ad)
    if cluster_key not in adata.obs:
        raise ValueError(f"cluster_key '{cluster_key}' was not found in input h5ad")
    by_cluster = {str(card["cluster_id"]): card for card in cards}
    clusters = adata.obs[cluster_key].astype(str)
    prefix = "scrna_annotate_audit"
    adata.obs[f"{prefix}_final_label"] = pd.Categorical([by_cluster.get(value, {}).get("final", {}).get("label", "Unknown") for value in clusters])
    adata.obs[f"{prefix}_final_broad_label"] = pd.Categorical([by_cluster.get(value, {}).get("final", {}).get("broad_label", "Unknown") for value in clusters])
    adata.obs[f"{prefix}_review_status"] = pd.Categorical([by_cluster.get(value, {}).get("final", {}).get("review_status", "not_reviewed") for value in clusters])
    adata.obs[f"{prefix}_label_source"] = pd.Categorical([by_cluster.get(value, {}).get("final", {}).get("label_source", "draft") for value in clusters])
    adata.obs[f"{prefix}_suggested_label"] = pd.Categorical([by_cluster.get(value, {}).get("suggested_label", "Unknown") for value in clusters])
    adata.obs[f"{prefix}_agreement_level"] = pd.Categorical([by_cluster.get(value, {}).get("agreement_level", "insufficient_evidence") for value in clusters])
    adata.obs[f"{prefix}_confidence"] = pd.Categorical([by_cluster.get(value, {}).get("confidence", "unknown") for value in clusters])
    adata.uns[prefix] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "cluster_key": cluster_key,
        "annotation_audit_cards_json": json.dumps(cards, sort_keys=True),
    }
    output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(output_h5ad)


def load_label_aliases(path: Path) -> dict[str, dict[str, str]]:
    aliases: dict[str, dict[str, str]] = {}
    if not path.exists():
        return aliases
    for row in read_csv_dicts(path):
        raw = canonical_key(row.get("raw_label", ""))
        normalized = clean_label(row.get("normalized_label"))
        broad = clean_label(row.get("broad_label")) or normalized
        if raw and normalized:
            aliases[raw] = {"normalized_label": normalized, "broad_label": broad}
            aliases[canonical_key(normalized)] = {"normalized_label": normalized, "broad_label": broad}
    return aliases


def normalize_label(value: Any, aliases: dict[str, dict[str, str]]) -> dict[str, str]:
    text = clean_label(value)
    key = canonical_key(text)
    if not key or key in NO_LABELS:
        return {"normalized_label": "unknown", "broad_label": "Unknown"}
    if key in aliases:
        return dict(aliases[key])
    broad = infer_broad_label(key)
    return {"normalized_label": pretty_label(key), "broad_label": broad}


def canonical_key(value: Any) -> str:
    text = str(value or "").lower().replace("+", " positive ")
    text = re.sub(r"[\-_/(),;:]+", " ", text)
    words = [word[:-1] if word.endswith("s") and len(word) > 3 else word for word in text.split()]
    return " ".join(words)


def pretty_label(canonical: str) -> str:
    special = {"t": "T", "b": "B", "nk": "NK", "cd4": "CD4", "cd8": "CD8"}
    return " ".join(special.get(word, word.capitalize()) for word in canonical.split())


def infer_broad_label(canonical: str) -> str:
    if "platelet" in canonical or "megakaryocyte" in canonical:
        return "Platelet/megakaryocyte"
    if any(term in canonical for term in ["monocyte", "macrophage", "dendritic", "neutrophil", "myeloid"]):
        return "Myeloid"
    if " t cell" in f" {canonical}" or canonical.startswith("t cell") or "nk cell" in canonical:
        return "T/NK cell"
    if "b cell" in canonical or "plasma" in canonical:
        return "B cell"
    if "endothelial" in canonical:
        return "Endothelial"
    if "fibroblast" in canonical or "stromal" in canonical or "smooth muscle" in canonical:
        return "Stromal"
    if "epithelial" in canonical:
        return "Epithelial"
    if "erythroid" in canonical or "erythrocyte" in canonical:
        return "Erythroid"
    return pretty_label(canonical)


def confidence_weight(value: Any) -> float:
    text = canonical_key(value)
    if "high" in text or "accepted" in text:
        return 3.0
    if "medium" in text or "moderate" in text or "review candidate" in text:
        return 2.0
    if "low" in text:
        return 1.0
    return 1.5


def score_from_prediction(prediction: dict[str, Any]) -> float | str:
    for key in ["top_probability", "max_probability", "mean_probability", "top_score", "score", "top_label_fraction"]:
        value = prediction.get(key)
        if value not in {None, ""}:
            return float_or_blank(value)
    return ""


def score_name_from_prediction(prediction: dict[str, Any]) -> str:
    for key in ["top_probability", "max_probability", "mean_probability", "top_score", "score", "top_label_fraction"]:
        if prediction.get(key) not in {None, ""}:
            return key
    return ""


def compact_evidence(evidence: Any) -> str:
    if isinstance(evidence, str):
        return evidence
    if not isinstance(evidence, list):
        return ""
    parts = []
    for item in evidence[:3]:
        if isinstance(item, dict):
            fields = []
            for key in ["evidence_type", "matched_genes", "matched_positive_genes", "missing_genes", "provider_score_name"]:
                if item.get(key):
                    fields.append(f"{key}={item[key]}")
            if fields:
                parts.append("; ".join(fields))
    return " | ".join(parts)


def provider_resources(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for provider in providers:
        payload = provider["payload"]
        rows.append(
            {
                "role": "annotation_result",
                "id": provider["method_id"],
                "template": provider["template_name"],
                "source_template": provider.get("source_template") or provider["template_name"],
                "method_family": provider.get("method_family") or provider["method_id"],
                "display_name": provider.get("display_name") or provider["method_id"],
                "path": str(provider["path"]),
                "sha256": sha256_file(provider["path"]),
                "run_state": payload.get("run", {}).get("state", ""),
            }
        )
    return rows


def render_report() -> None:
    report_src = TEMPLATE_DIR / "report.qmd"
    report_dst = RESULTS_DIR / "report.qmd"
    if report_src.exists():
        shutil.copyfile(report_src, report_dst)
    quarto = shutil.which("quarto")
    if quarto is None:
        write_fallback_report(RESULTS_DIR / "report.html")
        return
    try:
        subprocess.run([quarto, "render", str(report_dst), "--output", "report.html"], cwd=RESULTS_DIR, check=True)
    except Exception as exc:
        progress(f"quarto render skipped/failed: {exc}")
        write_fallback_report(RESULTS_DIR / "report.html")


def copy_review_app() -> None:
    app_src = TEMPLATE_DIR / "review_app.py"
    app_dst = RESULTS_DIR / "review_app.py"
    if app_src.exists():
        shutil.copyfile(app_src, app_dst)


def write_fallback_report(path: Path) -> None:
    path.write_text(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>scRNA-seq Annotation Audit</title>
<style>body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:900px;margin:3rem auto;padding:0 1rem;line-height:1.5}code{background:#f1f5f9;padding:.15rem .3rem;border-radius:4px}</style></head>
<body>
<h1>scRNA-seq Annotation Audit</h1>
<p>The audit data tables were generated successfully, but Quarto was not available to render the full interactive report.</p>
<p>Open <code>results/report.qmd</code> in an environment with Quarto, or inspect the CSV files in <code>results/tables/</code>.</p>
</body></html>
""",
        encoding="utf-8",
    )


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(value: Any, *, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def bool_param(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def clean_label(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def informative_label(value: Any) -> bool:
    return canonical_key(value) not in NO_LABELS


def empty_method(method_id: str) -> dict[str, Any]:
    return {"method_id": method_id, "method_family": method_id, "display_name": display_name_from_provider_id(method_id), "template_name": "", "source_template": "", "label": "", "normalized_label": "", "broad_label": "", "confidence": "", "review_status": "", "score": "", "score_name": "", "candidates": []}


def cluster_sort_key(value: Any) -> tuple[int, Any]:
    text = str(value)
    try:
        return (0, int(text))
    except ValueError:
        return (1, text)


def int_or_zero(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def float_or_blank(value: Any) -> float | str:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return ""


def sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
