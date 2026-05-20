#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
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
EXCEL_RESULT = RESULTS_DIR / "scrna_annotate_sctype_results.xlsx"
ANNOTATED_H5AD = RESULTS_DIR / "adata.annotated.h5ad"
SCHEMA_VERSION = "izkf_annotation_result.v1"
TEMPLATE_NAME = "scrna_annotate_sctype"
CATALOG_REQUIRED_FIELDS = [
    "catalog_id",
    "species",
    "organism_id",
    "tissue",
    "cell_type",
    "gene_symbol",
    "marker_role",
    "source",
    "citation",
    "evidence",
]
BUILTIN_CATALOGS = {
    "builtin:sctype_core": "config/default_catalogs/sctype_core.tsv",
    "sctype_core": "config/default_catalogs/sctype_core.tsv",
}
DOWNLOAD_CATALOGS = {
    "download:sctype": "sctype",
    "sctype": "sctype",
    "download:sctype_db": "sctype",
}
MARKER_FIELDS = ["cluster_id", "rank", "gene", "score", "log2fc", "pval_adj", "strength"]
CANDIDATE_FIELDS = [
    "cluster_id",
    "rank",
    "cell_type",
    "catalog_id",
    "species",
    "organism_id",
    "tissue",
    "source",
    "n_positive_matched",
    "n_negative_matched",
    "n_positive_catalog_genes",
    "n_negative_catalog_genes",
    "positive_coverage",
    "negative_coverage",
    "score",
    "confidence_bucket",
    "matched_positive_genes",
    "matched_negative_genes",
    "missing_positive_genes",
]
SUMMARY_FIELDS = [
    "cluster_id",
    "n_cells",
    "top_label",
    "confidence_bucket",
    "top_score",
    "matched_positive_genes",
    "matched_negative_genes",
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
class CatalogEntry:
    catalog_id: str
    species: str
    organism_id: str
    tissue: str
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

    organism = normalize_species(params["organism"])
    if organism not in {"mouse", "human"}:
        raise SystemExit(f"{TEMPLATE_NAME} supports organism=mouse or organism=human, got: {params['organism']!r}")
    organism_id = params.get("organism_id") or default_organism_id(organism)
    params["organism"] = organism
    params["organism_id"] = organism_id

    input_h5ad = resolve_input_h5ad(params)
    primary_catalog_path = resolve_catalog_path(params["primary_catalog"], warnings)

    progress(f"input h5ad: {input_h5ad}")
    progress(f"primary ScType catalog: {primary_catalog_path}")

    primary_entries = entries_for_context(read_catalog(primary_catalog_path), organism=organism, tissue=params.get("tissue"), warnings=warnings)
    if not primary_entries:
        raise SystemExit(f"primary catalog has no usable {organism} entries for the requested context")

    progress("ranking cluster markers with Scanpy")
    markers, cluster_sizes, _background_genes = compute_cluster_markers(
        input_h5ad=input_h5ad,
        cluster_key=params["cluster_key"],
        top_n=int(params["top_n_markers"]),
        expression_layer=params["expression_layer"],
        warnings=warnings,
    )
    marker_rows = marker_table_rows(markers, min_log2fc=float(params["min_log2fc"]))
    primary_rows = score_marker_catalog(
        marker_rows,
        primary_entries,
        min_log2fc=float(params["min_log2fc"]),
        catalog_role="primary_sctype",
        top_n=5,
    )
    cluster_predictions = cluster_predictions_from_candidates(primary_rows, cluster_sizes)
    summary_rows = summary_rows_from_predictions(cluster_predictions)

    if not marker_rows:
        warnings.append("No differential markers were produced.")
    if marker_rows and not primary_rows:
        warnings.append("Differential markers were produced, but no ScType candidates scored above zero.")

    write_csv(TABLES_DIR / "differential_markers.csv", marker_rows, MARKER_FIELDS)
    write_csv(TABLES_DIR / "sctype_candidates.csv", primary_rows, CANDIDATE_FIELDS)
    write_csv(TABLES_DIR / "cluster_annotation_summary.csv", summary_rows, SUMMARY_FIELDS)
    write_excel_workbook(
        EXCEL_RESULT,
        {
            "cluster_summary": summary_rows,
            "sctype_candidates": primary_rows,
            "differential_markers": marker_rows,
        },
    )

    artifacts: dict[str, Any] = {
        "report_html": "results/report.html",
        "report_qmd": "results/report.qmd",
        "excel_workbook": "results/scrna_annotate_sctype_results.xlsx",
        "tables": [
            "results/tables/differential_markers.csv",
            "results/tables/sctype_candidates.csv",
            "results/tables/cluster_annotation_summary.csv",
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
        "template": {
            "name": TEMPLATE_NAME,
            "version": "0.1.0",
        },
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
            "organism": organism,
            "organism_id": organism_id,
            "tissue": params.get("tissue") or None,
            "cluster_key": params["cluster_key"],
            "sample_key": params.get("sample_key") or None,
            "expression_layer": params["expression_layer"],
        },
        "method": {
            "name": "ScType-style marker-set scoring",
            "annotation_level": "cluster",
            "parameters": {
                "top_n_markers": int(params["top_n_markers"]),
                "min_log2fc": float(params["min_log2fc"]),
                "fdr_threshold": float(params["fdr_threshold"]),
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
                "step": "ScType marker scoring",
                "tool": "local Python ScType-style positive/negative marker overlap",
                "parameters": {
                    "primary_catalog": params["primary_catalog"],
                    "min_log2fc": float(params["min_log2fc"]),
                },
                "interpretation": "Positive marker matches support a candidate; negative marker matches penalize it. Scores are review evidence, not calibrated probabilities.",
            },
        ],
        "resources": resource_payload(primary_catalog_path, primary_entries, params["primary_catalog"], "primary_catalog"),
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
        "primary_catalog": analysis.get("primary_catalog", "download:sctype"),
        "top_n_markers": analysis.get("top_n_markers", 50),
        "min_log2fc": analysis.get("min_log2fc", 0.25),
        "fdr_threshold": analysis.get("fdr_threshold", 0.05),
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
        "primary_catalog": env("PRIMARY_CATALOG") or env("MARKER_CATALOG"),
        "top_n_markers": env("TOP_N_MARKERS"),
        "min_log2fc": env("MIN_LOG2FC"),
        "fdr_threshold": env("FDR_THRESHOLD"),
        "write_h5ad": env("WRITE_H5AD"),
    }
    for key, value in overrides.items():
        if value not in {"", None}:
            params[key] = value
    return params


def bool_param(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    raise SystemExit(f"Expected a boolean value, got: {value!r}")


def read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def env(name: str) -> str:
    return os.environ.get(name, "")


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
    raise SystemExit(
        "Set INPUT_H5AD before running scrna_annotate_sctype, or run scrna_prep first. "
        f"Expected default prep output at: {expected}"
    )


def resolve_catalog_path(value: Any, warnings: list[str]) -> Path:
    text = str(value or "").strip() or "download:sctype"
    if text in BUILTIN_CATALOGS:
        path = (TEMPLATE_DIR / BUILTIN_CATALOGS[text]).resolve()
        if not path.exists():
            raise SystemExit(f"built-in marker catalog is missing: {path}")
        return path
    if text in DOWNLOAD_CATALOGS:
        return download_catalog(DOWNLOAD_CATALOGS[text])
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (TEMPLATE_DIR / path).resolve()
    if path.exists():
        return path
    fallback = (TEMPLATE_DIR / "config" / "default_catalogs" / "sctype_core.tsv").resolve()
    if path.name == "sctype_core.tsv" and fallback.exists():
        warnings.append(f"Primary catalog '{path}' does not exist; using built-in smoke-test fixture: {fallback}")
        return fallback
    raise SystemExit(f"Primary marker catalog does not exist: {path}")


def download_catalog(catalog_id: str) -> Path:
    script = TEMPLATE_DIR / "scripts" / "download_catalog.py"
    refresh = os.environ.get("REFRESH_CATALOG", "").strip().lower() in {"1", "true", "yes", "on"}
    command = [sys.executable, str(script), catalog_id]
    if refresh:
        command.append("--refresh")
    progress(f"resolving downloadable catalog: {catalog_id}")
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    path = Path(completed.stdout.strip().splitlines()[-1]).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"downloaded marker catalog was not created: {path}")
    return path


def read_catalog(path: Path) -> list[CatalogEntry]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        missing = [field for field in CATALOG_REQUIRED_FIELDS if field not in fieldnames]
        if missing:
            raise SystemExit(f"marker catalog is missing required columns: {', '.join(missing)}")
        entries = [
            CatalogEntry(
                catalog_id=row.get("catalog_id", "").strip(),
                species=row.get("species", "").strip(),
                organism_id=row.get("organism_id", "").strip(),
                tissue=row.get("tissue", "").strip(),
                cell_type=row.get("cell_type", "").strip(),
                gene_symbol=row.get("gene_symbol", "").strip(),
                marker_role=normalize_marker_role(row.get("marker_role", "")),
                source=row.get("source", "").strip(),
                citation=row.get("citation", "").strip(),
                evidence=row.get("evidence", "").strip(),
            )
            for row in reader
            if row.get("cell_type", "").strip() and row.get("gene_symbol", "").strip()
        ]
    entries = [entry for entry in entries if entry.marker_role in {"positive", "negative"}]
    if not entries:
        raise SystemExit("marker catalog did not contain usable cell_type/gene_symbol rows")
    return entries


def entries_for_context(
    entries: list[CatalogEntry],
    *,
    organism: str,
    tissue: Any,
    warnings: list[str],
) -> list[CatalogEntry]:
    species_entries = [entry for entry in entries if normalize_species(entry.species) == organism]
    tissue_text = str(tissue or "").strip().lower()
    if not tissue_text:
        return species_entries
    exact = [entry for entry in species_entries if entry.tissue.strip().lower() == tissue_text]
    if exact:
        return exact
    fuzzy = [entry for entry in species_entries if tissue_text in entry.tissue.strip().lower()]
    if fuzzy:
        return fuzzy
    warnings.append(f"No catalog entries matched tissue={tissue!r}; using all {organism} catalog entries.")
    return species_entries


def compute_cluster_markers(
    *,
    input_h5ad: Path,
    cluster_key: str,
    top_n: int,
    expression_layer: str,
    warnings: list[str],
) -> tuple[list[MarkerGene], dict[str, int], set[str]]:
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
    elif expression_layer in {"X", "x"} and expression_matrix_looks_raw_counts(adata.X, adata=adata):
        warnings.append(
            "expression_layer is X and appears to contain raw counts. Use a normalized/log-transformed layer for marker ranking."
        )

    sc.settings.verbosity = 0
    with py_warnings.catch_warnings():
        py_warnings.filterwarnings(
            "ignore",
            message="DataFrame is highly fragmented.*",
            category=PerformanceWarning,
            module="scanpy.tools._rank_genes_groups",
        )
        sc.tl.rank_genes_groups(
            adata,
            groupby=cluster_key,
            method="wilcoxon",
            n_genes=top_n,
            layer=layer_arg,
            use_raw=use_raw,
            key_added="rank_genes",
        )
    background_genes = {normalize_gene(gene) for gene in adata.var_names if normalize_gene(gene)}
    return markers_from_rank_result(adata.uns["rank_genes"], top_n=top_n), cluster_sizes, background_genes


def markers_from_rank_result(rank_result: Any, *, top_n: int) -> list[MarkerGene]:
    names = rank_result.get("names")
    if names is None:
        return []
    groups = list(getattr(getattr(names, "dtype", None), "names", None) or [])
    markers: list[MarkerGene] = []
    for group in groups:
        genes = names[group]
        scores = rank_result.get("scores", {})
        logfcs = rank_result.get("logfoldchanges", {})
        pvals_adj = rank_result.get("pvals_adj", {})
        for index in range(min(top_n, len(genes))):
            gene = str(genes[index])
            if gene == "nan":
                continue
            markers.append(
                MarkerGene(
                    cluster_id=str(group),
                    rank=index + 1,
                    gene=gene,
                    score=optional_rank_float(scores, group, index),
                    log2fc=optional_rank_float(logfcs, group, index),
                    pval_adj=optional_rank_float(pvals_adj, group, index),
                )
            )
    return markers


def score_marker_catalog(
    marker_rows: list[dict[str, Any]],
    entries: list[CatalogEntry],
    *,
    min_log2fc: float,
    catalog_role: str,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    markers_by_cluster: dict[str, set[str]] = defaultdict(set)
    for row in marker_rows:
        if is_informative_marker_row(row, min_log2fc=min_log2fc):
            markers_by_cluster[str(row["cluster_id"])].add(normalize_gene(row["gene"]))

    catalog_groups: dict[tuple[str, str, str, str, str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"positive": set(), "negative": set()}
    )
    metadata: dict[tuple[str, str, str, str, str, str], CatalogEntry] = {}
    for entry in entries:
        key = (entry.cell_type, entry.catalog_id, entry.species, entry.organism_id, entry.tissue, entry.source)
        catalog_groups[key][entry.marker_role].add(normalize_gene(entry.gene_symbol))
        metadata.setdefault(key, entry)

    rows: list[dict[str, Any]] = []
    for cluster_id, marker_genes in sorted(markers_by_cluster.items(), key=lambda item: item[0]):
        scored: list[dict[str, Any]] = []
        for key, gene_sets in catalog_groups.items():
            cell_type, catalog_id, species, organism_id, tissue, source = key
            positive = {gene for gene in gene_sets["positive"] if gene}
            negative = {gene for gene in gene_sets["negative"] if gene}
            if not positive:
                continue
            matched_positive = sorted(marker_genes & positive)
            matched_negative = sorted(marker_genes & negative)
            if not matched_positive and not matched_negative:
                continue
            positive_coverage = len(matched_positive) / len(positive) if positive else 0.0
            negative_coverage = len(matched_negative) / len(negative) if negative else 0.0
            score = len(matched_positive) - len(matched_negative)
            if catalog_role == "primary_sctype" and score <= 0:
                continue
            entry = metadata[key]
            scored.append(
                {
                    "cluster_id": cluster_id,
                    "cell_type": cell_type,
                    "catalog_id": catalog_id,
                    "species": species,
                    "organism_id": organism_id,
                    "tissue": tissue,
                    "source": source,
                    "citation": entry.citation,
                    "n_positive_matched": len(matched_positive),
                    "n_negative_matched": len(matched_negative),
                    "n_positive_catalog_genes": len(positive),
                    "n_negative_catalog_genes": len(negative),
                    "positive_coverage": round(positive_coverage, 4),
                    "negative_coverage": round(negative_coverage, 4),
                    "score": round(float(score), 4),
                    "confidence_bucket": sctype_confidence(score, len(matched_positive), len(matched_negative)),
                    "matched_positive_genes": ", ".join(matched_positive),
                    "matched_negative_genes": ", ".join(matched_negative),
                    "missing_positive_genes": ", ".join(sorted(positive - marker_genes)[:20]),
                }
            )
        scored.sort(
            key=lambda item: (
                -float(item["score"]),
                -int(item["n_positive_matched"]),
                int(item["n_negative_matched"]),
                str(item["cell_type"]).lower(),
            )
        )
        for rank, row in enumerate(scored[:top_n], start=1):
            row["rank"] = rank
            rows.append(row)
    return rows


def cluster_predictions_from_candidates(
    primary_rows: list[dict[str, Any]],
    cluster_sizes: dict[str, int],
) -> list[dict[str, Any]]:
    primary_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in primary_rows:
        primary_by_cluster[str(row["cluster_id"])].append(row)

    predictions: list[dict[str, Any]] = []
    for cluster_id in sorted(set(cluster_sizes) | set(primary_by_cluster)):
        candidates = []
        for row in primary_by_cluster.get(cluster_id, []):
            evidence_items = [candidate_evidence_item(row, "primary_marker_score", supports_top_label=True)]
            candidates.append(
                {
                    "rank": int(row["rank"]),
                    "label_raw": row["cell_type"],
                    "label_normalized": normalize_label(row["cell_type"]),
                    "ontology_id": None,
                    "provider_score": float(row["score"]),
                    "provider_score_name": "sctype_positive_minus_negative_marker_matches",
                    "confidence_bucket": row["confidence_bucket"],
                    "evidence_items": evidence_items,
                }
            )
        top = candidates[0] if candidates else None
        predictions.append(
            {
                "cluster_id": cluster_id,
                "n_cells": cluster_sizes.get(cluster_id),
                "top_label": top["label_raw"] if top else None,
                "top_label_normalized": top["label_normalized"] if top else None,
                "confidence_bucket": top["confidence_bucket"] if top else "unknown",
                "review_status": "review candidate" if top else "no catalog-supported candidate",
                "candidates": candidates,
            }
        )
    return predictions


def candidate_evidence_item(row: dict[str, Any], evidence_type: str, *, supports_top_label: bool) -> dict[str, Any]:
    return {
        "evidence_type": evidence_type,
        "source": row["source"],
        "catalog_id": row["catalog_id"],
        "species": row["species"],
        "organism_id": row["organism_id"],
        "tissue": row["tissue"],
        "citation": row["citation"],
        "score": float(row["score"]),
        "supports_top_label": bool(supports_top_label),
        "matched_positive_genes": split_gene_list(row["matched_positive_genes"]),
        "matched_negative_genes": split_gene_list(row["matched_negative_genes"]),
        "missing_positive_genes": split_gene_list(row["missing_positive_genes"]),
        "n_positive_matched": int(row["n_positive_matched"]),
        "n_negative_matched": int(row["n_negative_matched"]),
        "n_positive_catalog_genes": int(row["n_positive_catalog_genes"]),
        "n_negative_catalog_genes": int(row["n_negative_catalog_genes"]),
        "positive_coverage": float(row["positive_coverage"]),
        "negative_coverage": float(row["negative_coverage"]),
    }


def summary_rows_from_predictions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for pred in predictions:
        top = pred.get("candidates", [None])[0] if pred.get("candidates") else None
        evidence_items = top.get("evidence_items", []) if top else []
        primary = evidence_items[0] if evidence_items else {}
        rows.append(
            {
                "cluster_id": pred["cluster_id"],
                "n_cells": pred.get("n_cells", ""),
                "top_label": pred.get("top_label") or "no ScType match",
                "confidence_bucket": pred.get("confidence_bucket") or "unknown",
                "top_score": top.get("provider_score", "") if top else "",
                "matched_positive_genes": ", ".join(primary.get("matched_positive_genes", [])),
                "matched_negative_genes": ", ".join(primary.get("matched_negative_genes", [])),
                "n_candidates": len(pred.get("candidates", [])),
                "review_status": pred.get("review_status", ""),
            }
        )
    return rows


def write_annotated_h5ad(
    *,
    input_h5ad: Path,
    output_h5ad: Path,
    cluster_predictions: list[dict[str, Any]],
    params: dict[str, Any],
) -> None:
    import pandas as pd
    import scanpy as sc

    adata = sc.read_h5ad(input_h5ad)
    cluster_key = str(params["cluster_key"])
    if cluster_key not in adata.obs:
        raise SystemExit(f"cluster_key '{cluster_key}' was not found in adata.obs")
    prediction_map = {str(pred["cluster_id"]): pred for pred in cluster_predictions}
    labels = []
    confidences = []
    review_statuses = []
    n_candidates = []
    top_scores = []
    matched_positive = []
    matched_negative = []
    for cluster_id in adata.obs[cluster_key].astype(str):
        pred = prediction_map.get(str(cluster_id), {})
        candidates = pred.get("candidates") or []
        top = candidates[0] if candidates else None
        evidence_items = top.get("evidence_items", []) if top else []
        primary = evidence_items[0] if evidence_items else {}
        labels.append(pred.get("top_label") or "no ScType match")
        confidences.append(pred.get("confidence_bucket") or "unknown")
        review_statuses.append(pred.get("review_status") or "no catalog-supported candidate")
        n_candidates.append(len(candidates))
        top_scores.append(top.get("provider_score") if top else float("nan"))
        matched_positive.append(", ".join(primary.get("matched_positive_genes", [])) if primary else "")
        matched_negative.append(", ".join(primary.get("matched_negative_genes", [])) if primary else "")

    adata.obs["scrna_annotate_sctype_label"] = pd.Categorical(labels)
    adata.obs["scrna_annotate_sctype_confidence"] = pd.Categorical(confidences)
    adata.obs["scrna_annotate_sctype_review_status"] = pd.Categorical(review_statuses)
    adata.obs["scrna_annotate_sctype_n_candidates"] = n_candidates
    adata.obs["scrna_annotate_sctype_top_score"] = top_scores
    adata.obs["scrna_annotate_sctype_matched_positive_genes"] = matched_positive
    adata.obs["scrna_annotate_sctype_matched_negative_genes"] = matched_negative
    adata.uns["scrna_annotate_sctype"] = {
        "schema_version": SCHEMA_VERSION,
        "cluster_key": cluster_key,
        "label_column": "scrna_annotate_sctype_label",
        "confidence_column": "scrna_annotate_sctype_confidence",
        "cluster_predictions_json": json.dumps(cluster_predictions, sort_keys=True),
    }
    output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(output_h5ad)


def resource_payload(path: Path | None, entries: list[CatalogEntry], configured_id: Any, role: str) -> list[dict[str, Any]]:
    if path is None:
        return []
    return [
        {
            "role": role,
            "id": str(configured_id or path.stem),
            "path": str(path),
            "sha256": sha256_file(path),
            "species": sorted({normalize_species(entry.species) for entry in entries if entry.species}),
            "n_rows": len(entries),
            "sources": sorted({entry.source for entry in entries if entry.source}),
        }
    ]


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


def write_excel_workbook(path: Path, sheets: dict[str, list[dict[str, Any]]]) -> None:
    try:
        import pandas as pd
    except ImportError:
        progress("pandas is not available; Excel workbook was not written")
        return
    try:
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
        progress("openpyxl is not available; Excel workbook was not written")


def safe_excel_sheet_name(value: str) -> str:
    return str(value).replace("/", "_").replace("\\", "_").replace("*", "_").replace("?", "_")[:31]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def expression_matrix_looks_raw_counts(matrix: Any, *, adata: Any) -> bool:
    if "log1p" in getattr(adata, "uns", {}):
        return False
    try:
        import numpy as np
        from scipy import sparse

        sample = matrix[: min(matrix.shape[0], 500), : min(matrix.shape[1], 500)]
        values = sample.data if sparse.issparse(sample) else np.asarray(sample).ravel()
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values)]
        values = values[values > 0]
        if values.size == 0:
            return False
        if values.size > 10000:
            values = values[:10000]
        integer_fraction = float(np.mean(np.isclose(values, np.round(values))))
        return integer_fraction > 0.98 and float(np.nanmax(values)) > 50
    except Exception:
        return False


def optional_rank_float(values: Any, group: str, index: int) -> float | None:
    try:
        value = float(values[group][index])
    except Exception:
        return None
    return value if value == value else None


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


def is_informative_marker_row(row: dict[str, Any], *, min_log2fc: float) -> bool:
    log2fc = parse_float(row.get("log2fc"), default=0.0)
    score = parse_float(row.get("score"), default=0.0)
    return score > 0 and log2fc >= min_log2fc


def marker_strength(marker: MarkerGene, *, min_log2fc: float) -> str:
    pval_adj = marker.pval_adj if marker.pval_adj is not None else 1.0
    log2fc = marker.log2fc if marker.log2fc is not None else 0.0
    score = marker.score if marker.score is not None else 0.0
    if pval_adj < 0.01 and log2fc >= max(1.0, min_log2fc) and score > 0:
        return "strong"
    if pval_adj < 0.05 and log2fc >= min_log2fc and score > 0:
        return "moderate"
    return "weak"


def sctype_confidence(score: float, n_positive: int, n_negative: int) -> str:
    if score >= 3 and n_positive >= 3 and n_negative == 0:
        return "high"
    if score >= 2 and n_positive >= 2:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def normalize_marker_role(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"positive", "pos", "+", "marker"}:
        return "positive"
    if text in {"negative", "neg", "-", "anti_marker", "exclude"}:
        return "negative"
    return text


def normalize_species(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    aliases = {
        "mus musculus": "mouse",
        "mmusculus": "mouse",
        "mmu": "mouse",
        "ncbitaxon:10090": "mouse",
        "homo sapiens": "human",
        "hsapiens": "human",
        "hsa": "human",
        "ncbitaxon:9606": "human",
    }
    return aliases.get(text, text)


def default_organism_id(organism: str) -> str:
    return {"mouse": "NCBITaxon:10090", "human": "NCBITaxon:9606"}[organism]


def normalize_gene(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_label(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def labels_match(left: Any, right: Any) -> bool:
    return normalize_label(left).rstrip("s") == normalize_label(right).rstrip("s")


def cluster_sort_key(value: Any) -> tuple[int, int | str]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def split_gene_list(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def parse_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


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


try:
    from pandas.errors import PerformanceWarning
except ImportError:
    PerformanceWarning = Warning


if __name__ == "__main__":
    raise SystemExit(main())
