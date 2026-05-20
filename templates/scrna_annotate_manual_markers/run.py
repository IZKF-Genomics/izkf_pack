#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import tomllib
import warnings as py_warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = Path(os.environ.get("LINKAR_PROJECT_DIR", TEMPLATE_DIR.parent)).resolve()
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
TABLES_DIR = RESULTS_DIR / "tables"
CONFIG_DIR = TEMPLATE_DIR / "config"
EXCEL_RESULT = RESULTS_DIR / "scrna_annotate_manual_markers_results.xlsx"
ANNOTATED_H5AD = RESULTS_DIR / "adata.annotated.h5ad"
SCHEMA_VERSION = "izkf_annotation_result.v1"
TEMPLATE_NAME = "scrna_annotate_manual_markers"
MARKER_FIELDS = ["cluster_id", "rank", "gene", "score", "log2fc", "pval_adj", "strength"]
CATALOG_FIELDS = ["cell_type", "gene_symbol", "marker_role", "source", "citation", "evidence"]
SCORE_FIELDS = [
    "cluster_id",
    "rank",
    "cell_type",
    "n_marker_genes",
    "n_present_genes",
    "mean_score",
    "mean_zscore",
    "score_margin",
    "confidence_bucket",
    "matched_genes",
    "missing_genes",
]
SUMMARY_FIELDS = [
    "cluster_id",
    "n_cells",
    "top_label",
    "confidence_bucket",
    "top_score",
    "score_margin",
    "matched_genes",
    "n_candidates",
    "review_status",
]


@dataclass(frozen=True)
class MarkerGene:
    cluster_id: str
    rank: int
    gene: str
    score: float | None
    log2fc: float | None
    pval_adj: float | None


@dataclass(frozen=True)
class ManualMarker:
    cell_type: str
    gene_symbol: str
    marker_role: str
    source: str
    citation: str
    evidence: str


def progress(message: str) -> None:
    print(f"[{TEMPLATE_NAME}] {message}", flush=True)


def main() -> int:
    started_at = utc_now()
    params = load_params()
    warnings: list[str] = []
    errors: list[str] = []

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    input_h5ad = resolve_input_h5ad(params)
    marker_catalog = resolve_path(params["marker_catalog"], base=TEMPLATE_DIR, required_name="MARKER_CATALOG")
    progress(f"input h5ad: {input_h5ad}")
    progress(f"manual marker catalog: {marker_catalog}")

    catalog_entries = read_marker_catalog(marker_catalog)
    progress("ranking cluster markers with Scanpy")
    markers, cluster_sizes = compute_cluster_markers(
        input_h5ad=input_h5ad,
        cluster_key=params["cluster_key"],
        top_n=int(params["top_n_markers"]),
        expression_layer=params["expression_layer"],
        warnings=warnings,
    )
    marker_rows = marker_table_rows(markers, min_log2fc=float(params["min_log2fc"]))

    progress("scoring manual marker programs")
    score_rows, catalog_rows, score_warnings = score_manual_markers(
        input_h5ad=input_h5ad,
        entries=catalog_entries,
        cluster_key=params["cluster_key"],
        expression_layer=params["score_layer"] or params["expression_layer"],
        score_method=params["score_method"],
        min_score_margin=float(params["min_score_margin"]),
    )
    warnings.extend(score_warnings)
    cluster_predictions = cluster_predictions_from_scores(score_rows, cluster_sizes)
    summary_rows = summary_rows_from_predictions(cluster_predictions)

    if not marker_rows:
        warnings.append("No differential markers were produced.")
    if not score_rows:
        warnings.append("No manual marker score rows were produced.")

    write_csv(TABLES_DIR / "differential_markers.csv", marker_rows, MARKER_FIELDS)
    write_csv(TABLES_DIR / "manual_marker_catalog.csv", catalog_rows, CATALOG_FIELDS)
    write_csv(TABLES_DIR / "manual_marker_scores.csv", score_rows, SCORE_FIELDS)
    write_csv(TABLES_DIR / "cluster_annotation_summary.csv", summary_rows, SUMMARY_FIELDS)
    write_sample_composition(input_h5ad, params["cluster_key"], params.get("sample_key"), summary_rows)
    write_excel_workbook(
        EXCEL_RESULT,
        {
            "cluster_summary": summary_rows,
            "manual_marker_scores": score_rows,
            "manual_marker_catalog": catalog_rows,
            "sample_composition": read_csv_dicts(TABLES_DIR / "sample_composition.csv"),
            "differential_markers": marker_rows,
        },
    )

    artifacts: dict[str, Any] = {
        "report_html": "results/report.html",
        "report_qmd": "results/report.qmd",
        "excel_workbook": "results/scrna_annotate_manual_markers_results.xlsx",
        "tables": [
            "results/tables/cluster_annotation_summary.csv",
            "results/tables/manual_marker_scores.csv",
            "results/tables/manual_marker_catalog.csv",
            "results/tables/sample_composition.csv",
            "results/tables/differential_markers.csv",
        ],
    }
    if bool_param(params["write_h5ad"]):
        progress("writing annotated h5ad")
        write_annotated_h5ad(
            input_h5ad=input_h5ad,
            output_h5ad=ANNOTATED_H5AD,
            cluster_predictions=cluster_predictions,
            params=params,
        )
        artifacts["annotated_h5ad"] = "results/adata.annotated.h5ad"

    state = "failed" if errors else "completed_with_warnings" if warnings else "completed"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "template": {"name": TEMPLATE_NAME, "version": "0.1.0"},
        "run": {
            "state": state,
            "warnings": warnings,
            "errors": errors,
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
            "name": "Manual marker score annotation",
            "annotation_level": "cluster",
            "parameters": {
                "marker_catalog": params["marker_catalog"],
                "score_layer": params["score_layer"] or params["expression_layer"],
                "score_method": params["score_method"],
                "top_n_markers": int(params["top_n_markers"]),
                "min_log2fc": float(params["min_log2fc"]),
                "min_score_margin": float(params["min_score_margin"]),
            },
        },
        "methods": [
            {
                "step": "Differential marker ranking",
                "tool": "scanpy.tl.rank_genes_groups",
                "parameters": {
                    "groupby": params["cluster_key"],
                    "method": "wilcoxon",
                    "n_genes": int(params["top_n_markers"]),
                    "expression_layer": params["expression_layer"],
                },
            },
            {
                "step": "Manual marker score annotation",
                "tool": "scanpy.tl.score_genes plus cluster mean z-score ranking",
                "parameters": {
                    "score_layer": params["score_layer"] or params["expression_layer"],
                    "score_method": params["score_method"],
                    "min_score_margin": float(params["min_score_margin"]),
                },
                "interpretation": "Each marker program is scored per cell; clusters are assigned to the marker program with the highest mean z-score. Scores are review evidence, not calibrated probabilities.",
            },
        ],
        "resources": [
            {
                "role": "manual_marker_catalog",
                "id": str(params["marker_catalog"]),
                "path": str(marker_catalog),
                "sha256": sha256_file(marker_catalog),
                "n_rows": len(catalog_rows),
                "sources": sorted({row["source"] for row in catalog_rows if row.get("source")}),
            }
        ],
        "cluster_predictions": cluster_predictions,
        "cell_predictions": None,
        "artifacts": artifacts,
    }
    write_json(RESULTS_DIR / "annotation_result.json", payload)
    render_report()
    payload["run"]["completed_at"] = utc_now()
    write_json(RESULTS_DIR / "annotation_result.json", payload)
    progress(f"done: {RESULTS_DIR / 'report.html'}")
    return 0


def load_params() -> dict[str, Any]:
    config = read_toml(CONFIG_DIR / "dataset.toml")
    dataset = dict(config.get("dataset", {}))
    analysis = dict(config.get("analysis", {}))
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
        "marker_catalog": analysis.get("marker_catalog", "config/marker_genes.csv"),
        "score_layer": analysis.get("score_layer", dataset.get("expression_layer", "X")),
        "score_method": analysis.get("score_method", "scanpy_score_genes"),
        "top_n_markers": analysis.get("top_n_markers", 50),
        "min_log2fc": analysis.get("min_log2fc", 0.25),
        "min_score_margin": analysis.get("min_score_margin", 0.15),
        "write_h5ad": outputs.get("write_h5ad", True),
    }
    overrides = {
        "input_h5ad": env("INPUT_H5AD"),
        "input_source_template": env("INPUT_SOURCE_TEMPLATE"),
        "organism": env("ORGANISM"),
        "organism_id": env("ORGANISM_ID"),
        "tissue": env("TISSUE"),
        "cluster_key": env("CLUSTER_KEY"),
        "sample_key": env("SAMPLE_ID_KEY") or env("SAMPLE_KEY"),
        "expression_layer": env("EXPRESSION_LAYER"),
        "marker_catalog": env("MARKER_CATALOG") or env("MARKER_GENES"),
        "score_layer": env("SCORE_LAYER"),
        "score_method": env("SCORE_METHOD"),
        "top_n_markers": env("TOP_N_MARKERS"),
        "min_log2fc": env("MIN_LOG2FC"),
        "min_score_margin": env("MIN_SCORE_MARGIN"),
        "write_h5ad": env("WRITE_H5AD"),
    }
    for key, value in overrides.items():
        if value not in {"", None}:
            params[key] = value
    if str(params["score_method"]).strip() != "scanpy_score_genes":
        raise SystemExit("Only score_method='scanpy_score_genes' is implemented in v1.")
    return params


def read_marker_catalog(path: Path) -> list[ManualMarker]:
    suffix = path.suffix.lower()
    delimiter = "\t" if suffix in {".tsv", ".tab"} else ","
    with path.open(newline="") as handle:
        sample = handle.readline()
        handle.seek(0)
        sample_fields = [field.strip().lower() for field in sample.split(delimiter)]
        has_header = any(name in sample_fields for name in ["cell_type", "celltype", "gene_symbol", "gene", "marker"])
        if has_header:
            reader = csv.DictReader(handle, delimiter=delimiter)
            rows = list(reader)
            entries = []
            for row in rows:
                cell_type = clean_text(row.get("cell_type") or row.get("celltype") or row.get("label") or row.get("annotation"))
                gene = clean_text(row.get("gene_symbol") or row.get("gene") or row.get("marker"))
                role = clean_text(row.get("marker_role") or row.get("role") or "positive").lower()
                if cell_type and gene and role in {"positive", "pos", "+", "marker"}:
                    entries.append(
                        ManualMarker(
                            cell_type=cell_type,
                            gene_symbol=gene,
                            marker_role="positive",
                            source=clean_text(row.get("source")) or "user_curated",
                            citation=clean_text(row.get("citation")) or "Manual marker list",
                            evidence=clean_text(row.get("evidence")) or "local",
                        )
                    )
        else:
            reader = csv.reader(handle, delimiter=delimiter)
            entries = []
            for row in reader:
                if len(row) < 2:
                    continue
                cell_type = clean_text(row[0])
                gene = clean_text(row[1])
                if cell_type and gene:
                    entries.append(ManualMarker(cell_type, gene, "positive", "user_curated", "Manual marker list", "local"))
    if not entries:
        raise SystemExit(f"manual marker catalog contains no usable marker rows: {path}")
    return deduplicate_markers(entries)


def deduplicate_markers(entries: list[ManualMarker]) -> list[ManualMarker]:
    seen = set()
    deduped = []
    for entry in entries:
        key = (entry.cell_type.lower(), normalize_gene(entry.gene_symbol), entry.marker_role)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def score_manual_markers(
    *,
    input_h5ad: Path,
    entries: list[ManualMarker],
    cluster_key: str,
    expression_layer: str,
    score_method: str,
    min_score_margin: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    import numpy as np
    import pandas as pd
    import scanpy as sc
    from scipy import sparse

    warnings: list[str] = []
    adata = sc.read_h5ad(input_h5ad)
    if cluster_key not in adata.obs:
        raise SystemExit(f"cluster_key '{cluster_key}' was not found in adata.obs")
    if expression_layer and expression_layer not in {"X", "x"}:
        if expression_layer in adata.layers:
            adata.X = adata.layers[expression_layer].copy()
        elif expression_layer == "raw" and adata.raw is not None:
            adata = adata.raw.to_adata()
            if cluster_key not in adata.obs:
                raise SystemExit(f"cluster_key '{cluster_key}' was not found after switching to adata.raw")
        else:
            warnings.append(f"score_layer '{expression_layer}' was not found; using X.")

    present_lookup = {normalize_gene(gene): str(gene) for gene in adata.var_names}
    grouped: dict[str, list[ManualMarker]] = defaultdict(list)
    for entry in entries:
        grouped[entry.cell_type].append(entry)

    catalog_rows: list[dict[str, Any]] = []
    score_columns = []
    for cell_type, cell_entries in grouped.items():
        present = []
        missing = []
        for entry in cell_entries:
            gene = present_lookup.get(normalize_gene(entry.gene_symbol))
            if gene:
                present.append(gene)
            else:
                missing.append(entry.gene_symbol)
            catalog_rows.append(
                {
                    "cell_type": entry.cell_type,
                    "gene_symbol": entry.gene_symbol,
                    "marker_role": entry.marker_role,
                    "source": entry.source,
                    "citation": entry.citation,
                    "evidence": entry.evidence,
                }
            )
        present = sorted(set(present), key=str.lower)
        if not present:
            warnings.append(f"No marker genes for '{cell_type}' were found in adata.var_names; skipping this label.")
            continue
        score_col = f"manual_marker_score__{safe_obs_name(cell_type)}"
        with py_warnings.catch_warnings():
            py_warnings.simplefilter("ignore")
            sc.tl.score_genes(adata, present, score_name=score_col)
        score_columns.append((cell_type, score_col, present, sorted(set(missing), key=str.lower), len(cell_entries)))

    if not score_columns:
        return [], catalog_rows, warnings

    score_matrix = adata.obs[[column for _, column, _, _, _ in score_columns]].astype(float)
    zscores = (score_matrix - score_matrix.mean(axis=0)) / score_matrix.std(axis=0, ddof=0).replace(0, np.nan)
    zscores = zscores.fillna(0)
    clusters = adata.obs[cluster_key].astype(str)
    rows: list[dict[str, Any]] = []
    for cluster_id in sorted(clusters.unique(), key=cluster_sort_key):
        mask = clusters == cluster_id
        cluster_rows = []
        raw_means = score_matrix.loc[mask].mean(axis=0)
        z_means = zscores.loc[mask].mean(axis=0)
        ordered = sorted(
            enumerate(score_columns),
            key=lambda item: float(z_means[item[1][1]]),
            reverse=True,
        )
        top_z = float(z_means[ordered[0][1][1]]) if ordered else 0.0
        second_z = float(z_means[ordered[1][1][1]]) if len(ordered) > 1 else 0.0
        margin = top_z - second_z
        for rank, (_, (cell_type, score_col, present, missing, n_marker_genes)) in enumerate(ordered, start=1):
            mean_z = float(z_means[score_col])
            row_margin = margin if rank == 1 else mean_z - top_z
            cluster_rows.append(
                {
                    "cluster_id": cluster_id,
                    "rank": rank,
                    "cell_type": cell_type,
                    "n_marker_genes": n_marker_genes,
                    "n_present_genes": len(present),
                    "mean_score": round(float(raw_means[score_col]), 5),
                    "mean_zscore": round(mean_z, 5),
                    "score_margin": round(float(row_margin), 5),
                    "confidence_bucket": manual_confidence(float(row_margin), rank, min_score_margin),
                    "matched_genes": ", ".join(present),
                    "missing_genes": ", ".join(missing),
                }
            )
        rows.extend(cluster_rows)
    return rows, catalog_rows, warnings


def cluster_predictions_from_scores(score_rows: list[dict[str, Any]], cluster_sizes: dict[str, int]) -> list[dict[str, Any]]:
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in score_rows:
        by_cluster[str(row["cluster_id"])].append(row)
    predictions = []
    for cluster_id in sorted(set(cluster_sizes) | set(by_cluster), key=cluster_sort_key):
        rows = sorted(by_cluster.get(cluster_id, []), key=lambda row: int(row["rank"]))
        candidates = [
            {
                "rank": int(row["rank"]),
                "label_raw": row["cell_type"],
                "label_normalized": normalize_label(row["cell_type"]),
                "ontology_id": None,
                "provider_score": float(row["mean_zscore"]),
                "provider_score_name": "manual_marker_cluster_mean_zscore",
                "confidence_bucket": row["confidence_bucket"],
                "evidence_items": [
                    {
                        "evidence_type": "manual_marker_score",
                        "source": "manual_marker_catalog",
                        "score": float(row["mean_zscore"]),
                        "score_margin": float(row["score_margin"]),
                        "matched_genes": split_gene_list(row["matched_genes"]),
                        "missing_genes": split_gene_list(row["missing_genes"]),
                        "n_marker_genes": int(row["n_marker_genes"]),
                        "n_present_genes": int(row["n_present_genes"]),
                    }
                ],
            }
            for row in rows[:5]
        ]
        top = candidates[0] if candidates else None
        predictions.append(
            {
                "cluster_id": cluster_id,
                "n_cells": cluster_sizes.get(cluster_id),
                "top_label": top["label_raw"] if top else None,
                "top_label_normalized": top["label_normalized"] if top else None,
                "confidence_bucket": top["confidence_bucket"] if top else "unknown",
                "review_status": "review candidate" if top else "no manual marker-supported candidate",
                "candidates": candidates,
            }
        )
    return predictions


def summary_rows_from_predictions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for pred in predictions:
        top = pred.get("candidates", [None])[0] if pred.get("candidates") else None
        evidence = top.get("evidence_items", [{}])[0] if top else {}
        rows.append(
            {
                "cluster_id": pred["cluster_id"],
                "n_cells": pred.get("n_cells", ""),
                "top_label": pred.get("top_label") or "no manual marker match",
                "confidence_bucket": pred.get("confidence_bucket") or "unknown",
                "top_score": top.get("provider_score", "") if top else "",
                "score_margin": evidence.get("score_margin", "") if evidence else "",
                "matched_genes": ", ".join(evidence.get("matched_genes", [])) if evidence else "",
                "n_candidates": len(pred.get("candidates", [])),
                "review_status": pred.get("review_status", ""),
            }
        )
    return rows


def compute_cluster_markers(
    *,
    input_h5ad: Path,
    cluster_key: str,
    top_n: int,
    expression_layer: str,
    warnings: list[str],
) -> tuple[list[MarkerGene], dict[str, int]]:
    import scanpy as sc

    adata = sc.read_h5ad(input_h5ad)
    if cluster_key not in adata.obs:
        raise SystemExit(f"cluster_key '{cluster_key}' was not found in adata.obs")
    adata.obs[cluster_key] = adata.obs[cluster_key].astype(str)
    cluster_sizes = {str(index): int(value) for index, value in adata.obs[cluster_key].value_counts().sort_index().items()}
    layer_arg = None
    use_raw = False
    if expression_layer and expression_layer not in {"X", "x"}:
        if expression_layer == "raw":
            use_raw = adata.raw is not None
            if not use_raw:
                warnings.append("expression_layer='raw' was requested, but adata.raw is not present; using X.")
        elif expression_layer in adata.layers:
            layer_arg = expression_layer
        else:
            warnings.append(f"expression_layer '{expression_layer}' was not found in adata.layers; using X.")
    sc.settings.verbosity = 0
    with py_warnings.catch_warnings():
        py_warnings.simplefilter("ignore")
        sc.tl.rank_genes_groups(
            adata,
            groupby=cluster_key,
            method="wilcoxon",
            n_genes=top_n,
            layer=layer_arg,
            use_raw=use_raw,
            key_added="rank_genes",
        )
    return markers_from_rank_result(adata.uns["rank_genes"], top_n=top_n), cluster_sizes


def markers_from_rank_result(rank_result: Any, *, top_n: int) -> list[MarkerGene]:
    names = rank_result.get("names")
    if names is None:
        return []
    groups = list(getattr(getattr(names, "dtype", None), "names", None) or [])
    markers = []
    for group in groups:
        genes = names[group]
        scores = rank_result.get("scores", {})
        logfcs = rank_result.get("logfoldchanges", {})
        pvals_adj = rank_result.get("pvals_adj", {})
        for index in range(min(top_n, len(genes))):
            gene = str(genes[index])
            if gene == "nan":
                continue
            markers.append(MarkerGene(str(group), index + 1, gene, optional_rank_float(scores, group, index), optional_rank_float(logfcs, group, index), optional_rank_float(pvals_adj, group, index)))
    return markers


def marker_table_rows(markers: list[MarkerGene], *, min_log2fc: float) -> list[dict[str, Any]]:
    return [
        {
            "cluster_id": marker.cluster_id,
            "rank": marker.rank,
            "gene": marker.gene,
            "score": round_optional(marker.score, 4),
            "log2fc": round_optional(marker.log2fc, 4),
            "pval_adj": round_optional(marker.pval_adj, 8),
            "strength": marker_strength(marker, min_log2fc=min_log2fc),
        }
        for marker in markers
    ]


def write_annotated_h5ad(*, input_h5ad: Path, output_h5ad: Path, cluster_predictions: list[dict[str, Any]], params: dict[str, Any]) -> None:
    import pandas as pd
    import scanpy as sc

    adata = sc.read_h5ad(input_h5ad)
    cluster_key = str(params["cluster_key"])
    prediction_map = {str(pred["cluster_id"]): pred for pred in cluster_predictions}
    labels = []
    confidences = []
    review_statuses = []
    n_candidates = []
    top_scores = []
    score_margins = []
    matched_genes = []
    for cluster_id in adata.obs[cluster_key].astype(str):
        pred = prediction_map.get(str(cluster_id), {})
        candidates = pred.get("candidates") or []
        top = candidates[0] if candidates else None
        evidence = top.get("evidence_items", [{}])[0] if top else {}
        labels.append(pred.get("top_label") or "no manual marker match")
        confidences.append(pred.get("confidence_bucket") or "unknown")
        review_statuses.append(pred.get("review_status") or "no manual marker-supported candidate")
        n_candidates.append(len(candidates))
        top_scores.append(top.get("provider_score") if top else float("nan"))
        score_margins.append(evidence.get("score_margin", float("nan")) if evidence else float("nan"))
        matched_genes.append(", ".join(evidence.get("matched_genes", [])) if evidence else "")
    adata.obs["scrna_annotate_manual_markers_label"] = pd.Categorical(labels)
    adata.obs["scrna_annotate_manual_markers_confidence"] = pd.Categorical(confidences)
    adata.obs["scrna_annotate_manual_markers_review_status"] = pd.Categorical(review_statuses)
    adata.obs["scrna_annotate_manual_markers_n_candidates"] = n_candidates
    adata.obs["scrna_annotate_manual_markers_top_score"] = top_scores
    adata.obs["scrna_annotate_manual_markers_score_margin"] = score_margins
    adata.obs["scrna_annotate_manual_markers_matched_genes"] = matched_genes
    adata.uns["scrna_annotate_manual_markers"] = {
        "schema_version": SCHEMA_VERSION,
        "cluster_key": cluster_key,
        "label_column": "scrna_annotate_manual_markers_label",
        "confidence_column": "scrna_annotate_manual_markers_confidence",
        "cluster_predictions_json": json.dumps(cluster_predictions, sort_keys=True),
    }
    output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(output_h5ad)


def write_sample_composition(input_h5ad: Path, cluster_key: str, sample_key: Any, summary_rows: list[dict[str, Any]]) -> None:
    import pandas as pd
    import scanpy as sc

    adata = sc.read_h5ad(input_h5ad, backed="r")
    try:
        if not sample_key or sample_key not in adata.obs:
            write_csv(TABLES_DIR / "sample_composition.csv", [], ["sample", "label", "count", "percent"])
            return
        label_map = {str(row["cluster_id"]): row["top_label"] for row in summary_rows}
        obs = pd.DataFrame(
            {
                "sample": adata.obs[sample_key].astype(str).values,
                "cluster_id": adata.obs[cluster_key].astype(str).values,
            }
        )
        obs["label"] = obs["cluster_id"].map(label_map).fillna("no manual marker match")
        counts = obs.groupby(["sample", "label"]).size().reset_index(name="count")
        counts["percent"] = counts.groupby("sample")["count"].transform(lambda values: values / values.sum() * 100)
        write_csv(TABLES_DIR / "sample_composition.csv", counts.to_dict("records"), ["sample", "label", "count", "percent"])
    finally:
        try:
            adata.file.close()
        except Exception:
            pass


def resolve_input_h5ad(params: dict[str, Any]) -> Path:
    value = str(params.get("input_h5ad") or "").strip()
    if value:
        return resolve_path(value, base=TEMPLATE_DIR, required_name="INPUT_H5AD")
    candidates = [
        PROJECT_DIR / "scrna_prep" / "results" / "adata.prep.h5ad",
        TEMPLATE_DIR.parent / "scrna_prep" / "results" / "adata.prep.h5ad",
    ]
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate.exists():
            params["input_h5ad"] = str(candidate)
            if not str(params.get("input_source_template") or "").strip():
                params["input_source_template"] = "scrna_prep"
            progress(f"INPUT_H5AD not set; using scrna_prep output: {candidate}")
            return candidate
    expected = candidates[0].expanduser().resolve()
    raise SystemExit(f"Set INPUT_H5AD before running {TEMPLATE_NAME}, or run scrna_prep first. Expected default prep output at: {expected}")


def resolve_path(value: Any, *, base: Path, required_name: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise SystemExit(f"Set {required_name} before running {TEMPLATE_NAME}.")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    if not path.exists():
        raise SystemExit(f"{required_name} does not exist: {path}")
    return path


def render_report() -> None:
    report_qmd = RESULTS_DIR / "report.qmd"
    shutil.copy2(TEMPLATE_DIR / "report.qmd", report_qmd)
    if shutil.which("quarto") is None:
        progress("Quarto is not available; report.qmd was written but report.html was not rendered")
        return
    subprocess.run(["quarto", "render", str(report_qmd.name), "--to", "html"], cwd=RESULTS_DIR, check=True)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def read_csv_dicts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_excel_workbook(path: Path, sheets: dict[str, list[dict[str, Any]]]) -> None:
    try:
        import pandas as pd
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet_name, rows in sheets.items():
                pd.DataFrame(rows).to_excel(writer, sheet_name=safe_excel_sheet_name(sheet_name), index=False)
            workbook = writer.book
            for worksheet in workbook.worksheets:
                worksheet.freeze_panes = "A2"
                worksheet.auto_filter.ref = worksheet.dimensions
                for column_cells in worksheet.columns:
                    max_length = max(len(str(cell.value or "")) for cell in column_cells)
                    worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 10), 60)
    except ImportError:
        progress("pandas/openpyxl is not available; Excel workbook was not written")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def bool_param(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    raise SystemExit(f"Expected a boolean value, got: {value!r}")


def env(name: str) -> str:
    return os.environ.get(name, "")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_obs_name(value: Any) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value)).strip("_")[:60] or "marker"


def safe_excel_sheet_name(value: str) -> str:
    return str(value).replace("/", "_").replace("\\", "_").replace("*", "_").replace("?", "_")[:31]


def normalize_gene(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_label(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def split_gene_list(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def cluster_sort_key(value: Any) -> tuple[int, int | str]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def manual_confidence(margin: float, rank: int, min_score_margin: float) -> str:
    if rank != 1:
        return "alternative"
    if margin >= max(0.5, min_score_margin * 2):
        return "high"
    if margin >= min_score_margin:
        return "medium"
    if margin > 0:
        return "low"
    return "ambiguous"


def marker_strength(marker: MarkerGene, *, min_log2fc: float) -> str:
    pval_adj = marker.pval_adj if marker.pval_adj is not None else 1.0
    log2fc = marker.log2fc if marker.log2fc is not None else 0.0
    score = marker.score if marker.score is not None else 0.0
    if pval_adj < 0.01 and log2fc >= max(1.0, min_log2fc) and score > 0:
        return "strong"
    if pval_adj < 0.05 and log2fc >= min_log2fc and score > 0:
        return "moderate"
    return "weak"


def optional_rank_float(values: Any, group: str, index: int) -> float | None:
    try:
        value = float(values[group][index])
    except Exception:
        return None
    return value if value == value else None


def round_optional(value: float | None, digits: int) -> float | str:
    if value is None:
        return ""
    return round(float(value), digits)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
