from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.io import relative_to, utc_now, write_csv, write_json
from lib.reports import render_qmd
from providers.marker_based.marker_signatures import MARKER_SIGNATURES


MARKER_TABLE_FIELDS = ["cluster_id", "rank", "gene", "score", "log2fc", "pval_adj", "strength"]
SIGNATURE_TABLE_FIELDS = [
    "cluster_id",
    "rank",
    "label",
    "source",
    "signature_species",
    "signature_scope",
    "n_matched",
    "n_signature_genes",
    "coverage",
    "jaccard",
    "score",
    "confidence_bucket",
    "matched_genes",
    "missing_genes",
]
STRENGTH_TABLE_FIELDS = ["cluster_id", "n_cells", "n_markers", "strong", "moderate", "weak"]
BUILTIN_SIGNATURE_SOURCE = {
    "id": "builtin_marker_signatures_v1",
    "species": "human",
    "scope": "broad_cell_classes",
    "score_type": "heuristic_overlap",
}
BUILTIN_SIGNATURE_SUPPORTED_ORGANISMS = {"human", "homo sapiens"}


@dataclass(frozen=True)
class MarkerGene:
    cluster_id: str
    rank: int
    gene: str
    score: float | None
    log2fc: float | None
    pval_adj: float | None


def run_provider(input_h5ad: Path, dataset: dict[str, Any], config: dict[str, Any], *, template_dir: Path, results_dir: Path) -> dict[str, Any]:
    provider_dir = results_dir / "providers" / "marker_based"
    tables_dir = provider_dir / "tables"
    logs_dir = provider_dir / "logs"
    provider_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    warnings: list[str] = []
    errors: list[str] = []
    cluster_key = str(dataset.get("cluster_key") or "leiden")
    top_n = int(config.get("top_n_markers") or 50)
    min_log2fc = float(config.get("min_log2fc") or 0.25)
    expression_layer = str(config.get("expression_layer") or dataset.get("expression_layer") or "X")
    validate_marker_inputs(dataset, expression_layer, warnings)

    markers: list[MarkerGene] = []
    cluster_sizes: dict[str, int] = {}
    try:
        markers, cluster_sizes = compute_cluster_markers(input_h5ad, cluster_key, top_n, expression_layer, warnings)
    except Exception as exc:
        errors.append(str(exc))

    marker_rows = marker_table_rows(markers, min_log2fc=min_log2fc)
    signature_source = built_in_signature_source_for_dataset(dataset, warnings)
    signature_rows = score_marker_signatures(markers, min_log2fc=min_log2fc, signature_source=signature_source)
    strength_rows = marker_strength_rows(markers, cluster_sizes, min_log2fc=min_log2fc)
    cluster_predictions = cluster_predictions_from_signatures(signature_rows, marker_rows, cluster_sizes)

    write_csv(tables_dir / "differential_markers.csv", marker_rows, MARKER_TABLE_FIELDS)
    write_csv(tables_dir / "marker_signatures.csv", signature_rows, SIGNATURE_TABLE_FIELDS)
    write_csv(tables_dir / "marker_strength_summary.csv", strength_rows, STRENGTH_TABLE_FIELDS)

    if not markers and not errors:
        warnings.append("No differential markers were produced.")
    if markers and signature_source is None:
        warnings.append("Differential markers were produced, but built-in human marker signatures were skipped for this organism.")
    elif markers and not signature_rows:
        warnings.append("Differential markers were produced, but no built-in marker signatures matched.")

    state = "failed" if errors else "completed_with_warnings" if warnings else "completed"
    qmd_path = provider_dir / "report.qmd"
    shutil.copy2(Path(__file__).with_name("report.qmd"), qmd_path)
    payload = {
        "schema_version": 1,
        "provider": {
            "id": "marker_based",
            "name": "Marker-based evidence",
            "group": "marker_based",
            "version": "0.1.0",
            "environment": {
                "manager": "pixi",
                "lockfile": "pixi.lock",
                "command": "python providers/marker_based/run.py",
            },
        },
        "input": {
            "h5ad": str(input_h5ad),
            "input_source_template": dataset.get("input_source_template") or None,
            "organism": dataset.get("organism") or None,
            "tissue": dataset.get("tissue") or None,
            "cluster_key": cluster_key,
            "sample_key": dataset.get("sample_key") or None,
            "batch_key": dataset.get("batch_key") or None,
            "condition_key": dataset.get("condition_key") or None,
            "gene_id_type": dataset.get("gene_id_type") or None,
            "expression_layer": expression_layer,
        },
        "input_validation": {
            "state": "ok" if not errors else "failed",
            "warnings": warnings,
            "genes_total": None,
            "genes_usable": len({row["gene"] for row in marker_rows}),
            "genes_in_vocab_fraction": None,
        },
        "status": {
            "state": state,
            "missing_config": [],
            "warnings": warnings,
            "errors": errors,
            "started_at": started_at,
            "completed_at": utc_now(),
        },
        "aggregation": None,
        "cluster_predictions": cluster_predictions,
        "cell_predictions": [],
        "artifacts": {
            "reports": [
                {"type": "quarto_report", "path": relative_to(qmd_path, template_dir), "description": "Marker-based provider report", "format": "qmd"},
            ],
            "tables": [
                {"type": "table", "path": relative_to(tables_dir / "differential_markers.csv", template_dir), "description": "Ranked marker genes by cluster", "format": "csv"},
                {"type": "table", "path": relative_to(tables_dir / "marker_signatures.csv", template_dir), "description": "Built-in marker signature matches", "format": "csv"},
                {"type": "table", "path": relative_to(tables_dir / "marker_strength_summary.csv", template_dir), "description": "Marker strength counts by cluster", "format": "csv"},
            ],
            "figures": [],
            "logs": [],
        },
        "methods": [
            {
                "step": "Differential expression",
                "tool": "scanpy.tl.rank_genes_groups",
                "parameters": {
                    "groupby": cluster_key,
                    "method": "wilcoxon",
                    "n_genes": top_n,
                    "expression_layer": expression_layer,
                },
            },
            {
                "step": "Marker signature scoring",
                "tool": "built-in marker signatures",
                "formula": "score = 0.65 * coverage + 0.35 * jaccard",
                "interpretation": "Heuristic evidence for review, not classifier probability or final annotation.",
                "signature_source": signature_source or BUILTIN_SIGNATURE_SOURCE,
                "parameters": {"min_log2fc": min_log2fc},
            },
        ],
        "enabled": True,
    }
    write_json(provider_dir / "annotation_result.json", payload)
    html_path = render_qmd(qmd_path, warnings)
    if html_path is not None:
        payload["artifacts"]["reports"].append(
            {"type": "html_report", "path": relative_to(html_path, template_dir), "description": "Rendered marker-based provider report", "format": "html"}
        )
    if warnings and state == "completed":
        payload["status"]["state"] = "completed_with_warnings"
    payload["status"]["warnings"] = warnings
    write_json(provider_dir / "annotation_result.json", payload)
    return payload


def validate_marker_inputs(dataset: dict[str, Any], expression_layer: str, warnings: list[str]) -> None:
    organism = normalize_text(dataset.get("organism"))
    gene_id_type = normalize_key(dataset.get("gene_id_type"))
    tissue = normalize_text(dataset.get("tissue"))
    if gene_id_type and gene_id_type not in {"gene_symbols", "auto"}:
        warnings.append(
            f"gene_id_type is '{dataset.get('gene_id_type')}'; built-in marker signatures expect gene symbols. "
            "Convert identifiers or provide a species-specific marker database before interpreting labels."
        )
    if organism and organism not in BUILTIN_SIGNATURE_SUPPORTED_ORGANISMS:
        warnings.append(
            f"organism is '{dataset.get('organism')}'. Built-in signatures are human marker signatures and will not be "
            "applied across species without an explicit species-specific or ortholog-mapped marker catalog."
        )
    if not tissue:
        warnings.append("tissue is not set; marker interpretation is context-light and should be reviewed manually.")
    if expression_layer in {"X", "x"}:
        warnings.append(
            "expression_layer is X. The marker provider assumes the selected matrix is normalized/log-transformed or otherwise suitable "
            "for Scanpy rank_genes_groups. If X contains raw counts, set expression_layer to a normalized layer."
        )


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def built_in_signature_source_for_dataset(dataset: dict[str, Any], warnings: list[str]) -> dict[str, str] | None:
    organism = normalize_text(dataset.get("organism"))
    if not organism:
        warnings.append("organism is not set; built-in human marker signatures were skipped to avoid cross-species misannotation.")
        return None
    if organism not in BUILTIN_SIGNATURE_SUPPORTED_ORGANISMS:
        return None
    return BUILTIN_SIGNATURE_SOURCE


def compute_cluster_markers(
    input_h5ad: Path,
    cluster_key: str,
    top_n: int,
    expression_layer: str,
    warnings: list[str],
) -> tuple[list[MarkerGene], dict[str, int]]:
    import scanpy as sc

    adata = sc.read_h5ad(input_h5ad)
    if cluster_key not in adata.obs:
        raise ValueError(f"cluster_key '{cluster_key}' was not found in .obs")
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


def markers_from_rank_result(rank_result: Any, top_n: int) -> list[MarkerGene]:
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


def optional_rank_float(values: Any, group: str, index: int) -> float | None:
    try:
        value = float(values[group][index])
    except Exception:
        return None
    return value if math.isfinite(value) else None


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


def score_marker_signatures(
    markers: list[MarkerGene],
    *,
    min_log2fc: float,
    top_n: int = 5,
    signature_source: dict[str, str] | None = BUILTIN_SIGNATURE_SOURCE,
) -> list[dict[str, Any]]:
    if signature_source is None:
        return []
    by_cluster: dict[str, set[str]] = {}
    for marker in markers:
        if is_informative_marker(marker, min_log2fc=min_log2fc):
            by_cluster.setdefault(marker.cluster_id, set()).add(marker.gene.upper())

    rows: list[dict[str, Any]] = []
    for cluster_id, query in sorted(by_cluster.items(), key=lambda item: item[0]):
        scored: list[dict[str, Any]] = []
        for label, genes in MARKER_SIGNATURES.items():
            signature_genes = {str(g).upper() for g in genes}
            matched = sorted(query & signature_genes)
            if not matched:
                continue
            missing = sorted(signature_genes - query)
            coverage = len(matched) / len(signature_genes) if signature_genes else 0.0
            jaccard = len(matched) / len(query | signature_genes) if query or signature_genes else 0.0
            score = (coverage * 0.65) + (jaccard * 0.35)
            scored.append(
                {
                    "cluster_id": cluster_id,
                    "label": label,
                    "source": signature_source["id"],
                    "signature_species": signature_source["species"],
                    "signature_scope": signature_source["scope"],
                    "n_matched": len(matched),
                    "n_signature_genes": len(signature_genes),
                    "coverage": round(coverage, 4),
                    "jaccard": round(jaccard, 4),
                    "score": round(score, 4),
                    "confidence_bucket": confidence_bucket(score, len(matched)),
                    "matched_genes": ", ".join(matched),
                    "missing_genes": ", ".join(missing[:20]),
                }
            )
        scored.sort(key=lambda item: (item["score"], item["n_matched"], item["coverage"]), reverse=True)
        for rank, row in enumerate(scored[:top_n], start=1):
            row["rank"] = rank
            rows.append(row)
    return rows


def marker_strength_rows(markers: list[MarkerGene], cluster_sizes: dict[str, int], *, min_log2fc: float) -> list[dict[str, Any]]:
    rows = []
    by_cluster: dict[str, list[MarkerGene]] = {}
    for marker in markers:
        by_cluster.setdefault(marker.cluster_id, []).append(marker)
    for cluster_id in sorted(set(cluster_sizes) | set(by_cluster)):
        cluster_markers = by_cluster.get(cluster_id, [])
        counts = {"strong": 0, "moderate": 0, "weak": 0}
        for marker in cluster_markers:
            counts[marker_strength(marker, min_log2fc=min_log2fc)] += 1
        rows.append(
            {
                "cluster_id": cluster_id,
                "n_cells": cluster_sizes.get(cluster_id, ""),
                "n_markers": len(cluster_markers),
                "strong": counts["strong"],
                "moderate": counts["moderate"],
                "weak": counts["weak"],
            }
        )
    return rows


def cluster_predictions_from_signatures(
    signature_rows: list[dict[str, Any]],
    marker_rows: list[dict[str, Any]],
    cluster_sizes: dict[str, int],
) -> list[dict[str, Any]]:
    signatures_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for row in signature_rows:
        signatures_by_cluster.setdefault(str(row["cluster_id"]), []).append(row)
    markers_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for row in marker_rows:
        markers_by_cluster.setdefault(str(row["cluster_id"]), []).append(row)

    predictions = []
    cluster_ids = sorted(set(cluster_sizes) | set(signatures_by_cluster) | set(markers_by_cluster))
    for cluster_id in cluster_ids:
        signatures = signatures_by_cluster.get(cluster_id, [])
        candidates = []
        for row in signatures:
            candidates.append(
                {
                    "label_raw": row["label"],
                    "label_normalized": row["label"],
                    "ontology_id": None,
                    "rank": int(row["rank"]),
                    "provider_score": float(row["score"]),
                    "provider_score_name": "builtin_marker_signature_overlap",
                    "confidence_bucket": row["confidence_bucket"],
                    "evidence": {
                        "source": row["source"],
                        "signature_species": row.get("signature_species"),
                        "signature_scope": row.get("signature_scope"),
                        "score_type": "heuristic_overlap",
                        "n_matched": row["n_matched"],
                        "n_signature_genes": row["n_signature_genes"],
                        "coverage": row["coverage"],
                        "jaccard": row["jaccard"],
                        "matched_genes": split_gene_list(row["matched_genes"]),
                        "missing_genes": split_gene_list(row["missing_genes"]),
                        "top_markers": markers_by_cluster.get(cluster_id, [])[:10],
                    },
                }
            )
        top = candidates[0] if candidates else None
        predictions.append(
            {
                "cluster_id": cluster_id,
                "top_label": top["label_raw"] if top else None,
                "confidence_bucket": top["confidence_bucket"] if top else "unknown",
                "n_cells": cluster_sizes.get(cluster_id),
                "candidates": candidates,
            }
        )
    return predictions


def split_gene_list(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def is_informative_marker(marker: MarkerGene, *, min_log2fc: float) -> bool:
    pval_adj = marker.pval_adj if marker.pval_adj is not None else 1.0
    log2fc = marker.log2fc if marker.log2fc is not None else 0.0
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


def confidence_bucket(score: float, n_matched: int) -> str:
    if score >= 0.28 and n_matched >= 3:
        return "high"
    if score >= 0.14 and n_matched >= 2:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def round_optional(value: float | None, digits: int) -> float | str:
    if value is None:
        return ""
    return round(float(value), digits)
