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
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
TABLES_DIR = RESULTS_DIR / "tables"
CONFIG_DIR = TEMPLATE_DIR / "config"
EXCEL_RESULT = RESULTS_DIR / "scrna_annotate_zebrafish_results.xlsx"
CATALOG_REQUIRED_FIELDS = [
    "catalog_id",
    "species",
    "organism_id",
    "tissue",
    "stage",
    "cell_type",
    "gene_symbol",
    "source",
    "citation",
    "evidence",
]
BUILTIN_CATALOGS = {
    "builtin:zebrafish_core": "config/default_catalogs/zebrafish_core.tsv",
    "zebrafish_core": "config/default_catalogs/zebrafish_core.tsv",
}
DOWNLOAD_CATALOGS = {
    "download:zcl_2_marker_list": "zcl_2_marker_list",
    "zcl_2_marker_list": "zcl_2_marker_list",
    "download:zcl_marker_list": "zcl_2_marker_list",
    "zcl_marker_list": "zcl_2_marker_list",
}
MARKER_FIELDS = ["cluster_id", "rank", "gene", "score", "log2fc", "pval_adj", "strength"]
MATCH_FIELDS = [
    "cluster_id",
    "rank",
    "cell_type",
    "catalog_id",
    "species",
    "organism_id",
    "tissue",
    "stage",
    "source",
    "citation",
    "n_matched",
    "n_cluster_markers",
    "n_catalog_genes",
    "n_background_genes",
    "coverage",
    "jaccard",
    "pval",
    "pval_adj",
    "score",
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
class CatalogEntry:
    catalog_id: str
    species: str
    organism_id: str
    tissue: str
    stage: str
    cell_type: str
    gene_symbol: str
    source: str
    citation: str
    evidence: str


def progress(message: str) -> None:
    print(f"[scrna_annotate_zebrafish] {message}", flush=True)


def main() -> int:
    started_at = utc_now()
    params = load_params()
    warnings: list[str] = []
    errors: list[str] = []

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    organism = normalize_species(params["organism"])
    if organism != "zebrafish":
        raise SystemExit(f"scrna_annotate_zebrafish requires ORGANISM=zebrafish/Danio rerio, got: {params['organism']!r}")

    input_h5ad = resolve_path(params["input_h5ad"], base=TEMPLATE_DIR, required_name="INPUT_H5AD")
    catalog_path = resolve_catalog_path(params["marker_catalog"], warnings)
    progress(f"input h5ad: {input_h5ad}")
    progress(f"marker catalog: {catalog_path}")
    if not params.get("tissue"):
        progress("tissue is not set; report will use context-light interpretation")
    if not params.get("stage"):
        progress("stage is not set; stage-specific catalog interpretation should be reviewed")

    catalog_entries = read_catalog(catalog_path)
    catalog_species = {normalize_species(entry.species) for entry in catalog_entries if entry.species}
    if catalog_species != {"zebrafish"}:
        raise SystemExit(f"marker catalog must contain only zebrafish entries; found: {sorted(catalog_species)}")

    progress("ranking cluster markers with Scanpy")
    markers, cluster_sizes, background_genes = compute_cluster_markers(
        input_h5ad=input_h5ad,
        cluster_key=params["cluster_key"],
        top_n=int(params["top_n_markers"]),
        expression_layer=params["expression_layer"],
        warnings=warnings,
    )
    marker_rows = marker_table_rows(markers, min_log2fc=float(params["min_log2fc"]))
    match_rows = score_catalog(
        marker_rows,
        catalog_entries,
        min_log2fc=float(params["min_log2fc"]),
        fdr_threshold=float(params["fdr_threshold"]),
        background_genes=background_genes,
    )
    cluster_predictions = cluster_predictions_from_matches(match_rows, cluster_sizes)
    summary_rows = summary_rows_from_predictions(cluster_predictions)

    if not marker_rows:
        warnings.append("No differential markers were produced.")
    if marker_rows and not match_rows:
        warnings.append("Differential markers were produced, but no zebrafish catalog entries matched.")

    write_csv(TABLES_DIR / "differential_markers.csv", marker_rows, MARKER_FIELDS)
    write_csv(TABLES_DIR / "catalog_matches.csv", match_rows, MATCH_FIELDS)
    write_csv(TABLES_DIR / "cluster_annotation_summary.csv", summary_rows, SUMMARY_FIELDS)
    write_excel_workbook(
        EXCEL_RESULT,
        {
            "cluster_summary": summary_rows,
            "catalog_matches": match_rows,
            "differential_markers": marker_rows,
        },
    )

    state = "failed" if errors else "completed_with_warnings" if warnings else "completed"
    payload = {
        "schema_version": 1,
        "template": "scrna_annotate_zebrafish",
        "input": {
            "h5ad": str(input_h5ad),
            "input_source_template": params.get("input_source_template") or None,
            "organism": "zebrafish",
            "organism_id": "NCBITaxon:7955",
            "tissue": params.get("tissue") or None,
            "stage": params.get("stage") or None,
            "cluster_key": params["cluster_key"],
            "sample_key": params.get("sample_key") or None,
            "expression_layer": params["expression_layer"],
        },
        "catalog": {
            "id": catalog_id_from_value(params["marker_catalog"], catalog_path),
            "path": str(catalog_path),
            "sha256": sha256_file(catalog_path),
            "species": "zebrafish",
            "n_rows": len(catalog_entries),
            "sources": sorted({entry.source for entry in catalog_entries if entry.source}),
        },
        "status": {
            "state": state,
            "warnings": warnings,
            "errors": errors,
            "started_at": started_at,
            "completed_at": utc_now(),
        },
        "cluster_predictions": cluster_predictions,
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
                "step": "Zebrafish marker catalog scoring",
                "tool": "local TSV marker catalog overlap",
                "parameters": {
                    "min_log2fc": float(params["min_log2fc"]),
                    "fdr_threshold": float(params["fdr_threshold"]),
                },
                "interpretation": "Hypergeometric marker-set enrichment with BH/FDR correction; evidence for review, not classifier probability or final annotation.",
            },
        ],
        "artifacts": {
            "report_html": "results/report.html",
            "report_qmd": "results/report.qmd",
            "excel_workbook": "results/scrna_annotate_zebrafish_results.xlsx",
            "tables": [
                "results/tables/differential_markers.csv",
                "results/tables/catalog_matches.csv",
                "results/tables/cluster_annotation_summary.csv",
            ],
        },
    }
    write_json(RESULTS_DIR / "annotation_result.json", payload)
    render_report()
    write_json(RESULTS_DIR / "annotation_result.json", payload)
    progress(f"done: {RESULTS_DIR / 'report.html'}")
    return 0


def load_params() -> dict[str, Any]:
    config = read_toml(CONFIG_DIR / "dataset.toml")
    dataset = dict(config.get("dataset", {}))
    analysis = dict(config.get("analysis", {}))
    params = {
        "input_h5ad": dataset.get("input_h5ad", ""),
        "input_source_template": dataset.get("input_source_template", ""),
        "organism": dataset.get("organism", "zebrafish"),
        "tissue": dataset.get("tissue", ""),
        "stage": dataset.get("stage", ""),
        "cluster_key": dataset.get("cluster_key", "leiden"),
        "sample_key": dataset.get("sample_key", "sample_id"),
        "expression_layer": dataset.get("expression_layer", "X"),
        "marker_catalog": analysis.get("marker_catalog", "config/marker_catalog.tsv"),
        "top_n_markers": analysis.get("top_n_markers", 50),
        "min_log2fc": analysis.get("min_log2fc", 0.25),
        "fdr_threshold": analysis.get("fdr_threshold", 0.05),
    }
    overrides = {
        "input_h5ad": env("INPUT_H5AD"),
        "input_source_template": env("INPUT_SOURCE_TEMPLATE"),
        "organism": env("ORGANISM"),
        "tissue": env("TISSUE"),
        "stage": env("STAGE"),
        "cluster_key": env("CLUSTER_KEY"),
        "sample_key": env("SAMPLE_ID_KEY") or env("SAMPLE_KEY"),
        "expression_layer": env("EXPRESSION_LAYER"),
        "marker_catalog": env("MARKER_CATALOG"),
        "top_n_markers": env("TOP_N_MARKERS"),
        "min_log2fc": env("MIN_LOG2FC"),
        "fdr_threshold": env("FDR_THRESHOLD"),
    }
    for key, value in overrides.items():
        if value not in {"", None}:
            params[key] = value
    return params


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
        raise SystemExit(f"Set {required_name} before running scrna_annotate_zebrafish.")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    if not path.exists():
        raise SystemExit(f"{required_name} does not exist: {path}")
    return path


def resolve_catalog_path(value: Any, warnings: list[str]) -> Path:
    text = str(value or "").strip()
    if not text:
        text = "builtin:zebrafish_core"
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

    fallback = fallback_builtin_catalog_for_missing_path(path)
    if fallback is not None:
        warnings.append(
            f"MARKER_CATALOG was set to '{path}', but the file does not exist. "
            f"Using built-in zebrafish catalog instead: {fallback}"
        )
        return fallback
    raise SystemExit(f"MARKER_CATALOG does not exist: {path}")


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


def catalog_id_from_value(value: Any, path: Path) -> str:
    text = str(value or "").strip()
    if text in BUILTIN_CATALOGS:
        return text
    if text in DOWNLOAD_CATALOGS:
        return text
    if "default_catalogs" in path.parts:
        return "builtin:zebrafish_core"
    return path.stem


def fallback_builtin_catalog_for_missing_path(path: Path) -> Path | None:
    if path.name not in {"marker_catalog.tsv", "zebrafish_core.tsv"}:
        return None
    fallback = (TEMPLATE_DIR / "config" / "default_catalogs" / "zebrafish_core.tsv").resolve()
    return fallback if fallback.exists() else None


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
                stage=row.get("stage", "").strip(),
                cell_type=row.get("cell_type", "").strip(),
                gene_symbol=row.get("gene_symbol", "").strip(),
                source=row.get("source", "").strip(),
                citation=row.get("citation", "").strip(),
                evidence=row.get("evidence", "").strip(),
            )
            for row in reader
            if row.get("cell_type", "").strip() and row.get("gene_symbol", "").strip()
        ]
    if not entries:
        raise SystemExit("marker catalog did not contain usable cell_type/gene_symbol rows")
    return entries


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


def score_catalog(
    marker_rows: list[dict[str, Any]],
    entries: list[CatalogEntry],
    *,
    min_log2fc: float,
    fdr_threshold: float,
    background_genes: set[str],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    markers_by_cluster: dict[str, set[str]] = defaultdict(set)
    for row in marker_rows:
        if is_informative_marker_row(row, min_log2fc=min_log2fc):
            markers_by_cluster[str(row["cluster_id"])].add(normalize_gene(row["gene"]))

    catalog_groups: dict[tuple[str, str, str, str, str, str, str], set[str]] = defaultdict(set)
    for entry in entries:
        key = (entry.cell_type, entry.catalog_id, entry.species, entry.organism_id, entry.tissue, entry.stage, entry.source)
        catalog_groups[key].add(normalize_gene(entry.gene_symbol))

    rows: list[dict[str, Any]] = []
    background = {gene for gene in background_genes if gene}
    background_size = len(background)
    for cluster_id, marker_genes in sorted(markers_by_cluster.items(), key=lambda item: item[0]):
        if not marker_genes or not background:
            continue
        marker_genes = marker_genes & background
        n_cluster_markers = len(marker_genes)
        if n_cluster_markers == 0:
            continue
        scored: list[dict[str, Any]] = []
        for (cell_type, catalog_id, species, organism_id, tissue, stage, source), catalog_genes in catalog_groups.items():
            catalog_genes = catalog_genes & background
            if not catalog_genes:
                continue
            matched = sorted(marker_genes & catalog_genes)
            if not matched:
                continue
            missing = sorted(catalog_genes - marker_genes)
            coverage = len(matched) / len(catalog_genes) if catalog_genes else 0.0
            jaccard = len(matched) / len(marker_genes | catalog_genes) if marker_genes or catalog_genes else 0.0
            pval = hypergeom_overrepresentation_pvalue(
                overlap=len(matched),
                population_size=background_size,
                success_states=len(catalog_genes),
                draws=n_cluster_markers,
            )
            scored.append(
                {
                    "cluster_id": cluster_id,
                    "cell_type": cell_type,
                    "catalog_id": catalog_id,
                    "species": species,
                    "organism_id": organism_id,
                    "tissue": tissue,
                    "stage": stage,
                    "source": source,
                    "citation": first_citation(entries, cell_type=cell_type, catalog_id=catalog_id, source=source),
                    "n_matched": len(matched),
                    "n_cluster_markers": n_cluster_markers,
                    "n_catalog_genes": len(catalog_genes),
                    "n_background_genes": background_size,
                    "coverage": round(coverage, 4),
                    "jaccard": round(jaccard, 4),
                    "pval": pval,
                    "matched_genes": ", ".join(matched),
                    "missing_genes": ", ".join(missing[:20]),
                }
            )
        scored = add_bh_fdr(scored)
        scored = [row for row in scored if row["pval_adj"] <= fdr_threshold]
        for row in scored:
            row["pval"] = round(row["pval"], 8)
            row["pval_adj"] = round(row["pval_adj"], 8)
            row["score"] = round(enrichment_score(row["pval_adj"]), 4)
            row["confidence_bucket"] = confidence_bucket(float(row["pval_adj"]), int(row["n_matched"]))
        scored.sort(key=lambda item: (item["pval_adj"], -item["n_matched"], -item["coverage"], item["cell_type"]))
        for rank, row in enumerate(scored[:top_n], start=1):
            row["rank"] = rank
            rows.append(row)
    return rows


def add_bh_fdr(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    m = len(rows)
    order = sorted(range(m), key=lambda index: float(rows[index]["pval"]))
    adjusted = [1.0] * m
    running_min = 1.0
    for reverse_rank, index in enumerate(reversed(order), start=1):
        rank = m - reverse_rank + 1
        value = min(1.0, float(rows[index]["pval"]) * m / rank)
        running_min = min(running_min, value)
        adjusted[index] = running_min
    for row, pval_adj in zip(rows, adjusted):
        row["pval_adj"] = pval_adj
    return rows


def enrichment_score(pval_adj: float) -> float:
    return -math.log10(max(float(pval_adj), 1e-300))


def hypergeom_overrepresentation_pvalue(
    *,
    overlap: int,
    population_size: int,
    success_states: int,
    draws: int,
) -> float:
    try:
        from scipy.stats import hypergeom

        return float(hypergeom.sf(overlap - 1, population_size, success_states, draws))
    except ImportError:
        return hypergeom_sf_exact(overlap, population_size, success_states, draws)


def hypergeom_sf_exact(overlap: int, population_size: int, success_states: int, draws: int) -> float:
    max_overlap = min(success_states, draws)
    if overlap <= 0:
        return 1.0
    if overlap > max_overlap or population_size <= 0:
        return 0.0
    denominator = log_comb(population_size, draws)
    terms = [
        log_comb(success_states, observed)
        + log_comb(population_size - success_states, draws - observed)
        - denominator
        for observed in range(overlap, max_overlap + 1)
        if 0 <= draws - observed <= population_size - success_states
    ]
    if not terms:
        return 0.0
    largest = max(terms)
    return min(1.0, math.exp(largest) * sum(math.exp(term - largest) for term in terms))


def log_comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


try:
    from pandas.errors import PerformanceWarning
except ImportError:
    PerformanceWarning = Warning


def cluster_predictions_from_matches(matches: list[dict[str, Any]], cluster_sizes: dict[str, int]) -> list[dict[str, Any]]:
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in matches:
        by_cluster[str(row["cluster_id"])].append(row)
    predictions: list[dict[str, Any]] = []
    for cluster_id in sorted(set(cluster_sizes) | set(by_cluster)):
        rows = by_cluster.get(cluster_id, [])
        candidates = [
            {
                "label_raw": row["cell_type"],
                "label_normalized": row["cell_type"],
                "rank": int(row["rank"]),
                "provider_score": float(row["score"]),
                "provider_score_name": "zebrafish_marker_catalog_enrichment_neg_log10_fdr",
                "confidence_bucket": row["confidence_bucket"],
                "evidence": {
                    "catalog_id": row["catalog_id"],
                    "species": row["species"],
                    "organism_id": row["organism_id"],
                    "tissue": row["tissue"],
                    "stage": row["stage"],
                    "source": row["source"],
                    "citation": row["citation"],
                    "matched_genes": split_gene_list(row["matched_genes"]),
                    "missing_genes": split_gene_list(row["missing_genes"]),
                    "n_cluster_markers": row["n_cluster_markers"],
                    "n_catalog_genes": row["n_catalog_genes"],
                    "n_background_genes": row["n_background_genes"],
                    "coverage": row["coverage"],
                    "jaccard": row["jaccard"],
                    "pval": row["pval"],
                    "pval_adj": row["pval_adj"],
                },
            }
            for row in rows
        ]
        top = candidates[0] if candidates else None
        predictions.append(
            {
                "cluster_id": cluster_id,
                "n_cells": cluster_sizes.get(cluster_id),
                "top_label": top["label_raw"] if top else None,
                "confidence_bucket": top["confidence_bucket"] if top else "unknown",
                "candidates": candidates,
            }
        )
    return predictions


def summary_rows_from_predictions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for pred in predictions:
        top = pred.get("candidates", [None])[0] if pred.get("candidates") else None
        evidence = top.get("evidence", {}) if top else {}
        rows.append(
            {
                "cluster_id": pred["cluster_id"],
                "n_cells": pred.get("n_cells", ""),
                "top_label": pred.get("top_label") or "no catalog match",
                "confidence_bucket": pred.get("confidence_bucket") or "unknown",
                "top_score": top.get("provider_score", "") if top else "",
                "matched_genes": ", ".join(evidence.get("matched_genes", [])),
                "n_candidates": len(pred.get("candidates", [])),
                "review_status": "review candidate" if top else "no catalog-supported candidate",
            }
        )
    return rows


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
                    adjusted = min(max(max_length + 2, 10), 60)
                    worksheet.column_dimensions[column_cells[0].column_letter].width = adjusted
    except ImportError:
        progress("openpyxl is not available; Excel workbook was not written")


def safe_excel_sheet_name(value: str) -> str:
    return str(value).replace("/", "_").replace("\\", "_").replace("*", "_").replace("?", "_")[:31]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def is_informative_marker_row(row: dict[str, Any], *, min_log2fc: float) -> bool:
    pval_adj = parse_float(row.get("pval_adj"), default=1.0)
    log2fc = parse_float(row.get("log2fc"), default=0.0)
    return pval_adj < 0.05 and log2fc >= min_log2fc


def marker_strength(marker: MarkerGene, *, min_log2fc: float) -> str:
    pval_adj = marker.pval_adj if marker.pval_adj is not None else 1.0
    log2fc = marker.log2fc if marker.log2fc is not None else 0.0
    score = marker.score if marker.score is not None else 0.0
    if pval_adj < 0.01 and log2fc >= max(1.0, min_log2fc) and score > 0:
        return "strong"
    if pval_adj < 0.05 and log2fc >= min_log2fc and score > 0:
        return "moderate"
    return "weak"


def confidence_bucket(pval_adj: float, n_matched: int) -> str:
    if pval_adj <= 0.01 and n_matched >= 3:
        return "high"
    if pval_adj <= 0.05:
        return "medium"
    if pval_adj <= 0.10:
        return "low"
    return "unknown"


def first_citation(entries: list[CatalogEntry], *, cell_type: str, catalog_id: str, source: str) -> str:
    for entry in entries:
        if entry.cell_type == cell_type and entry.catalog_id == catalog_id and entry.source == source and entry.citation:
            return entry.citation
    return ""


def normalize_species(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    aliases = {
        "danio rerio": "zebrafish",
        "drerio": "zebrafish",
        "dre": "zebrafish",
        "ncbitaxon:7955": "zebrafish",
    }
    return aliases.get(text, text)


def normalize_gene(value: Any) -> str:
    return str(value or "").strip().lower()


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


if __name__ == "__main__":
    raise SystemExit(main())
