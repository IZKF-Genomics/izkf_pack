from __future__ import annotations

import csv
import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.io import relative_to, utc_now, write_csv, write_json


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
    "n_catalog_genes",
    "coverage",
    "jaccard",
    "score",
    "confidence_bucket",
    "matched_genes",
    "missing_genes",
]


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


def run_provider(input_h5ad: Path, dataset: dict[str, Any], config: dict[str, Any], *, template_dir: Path, results_dir: Path) -> dict[str, Any]:
    provider_dir = results_dir / "providers" / "marker_catalog"
    tables_dir = provider_dir / "tables"
    provider_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    warnings: list[str] = []
    errors: list[str] = []
    missing_config: list[str] = []
    cluster_key = str(dataset.get("cluster_key") or "leiden")
    organism = normalize_species(dataset.get("organism"))
    catalog_path = resolve_catalog_path(template_dir, config.get("catalog_path"))
    resource_id = str(config.get("resource_id") or "").strip()
    configured_species = normalize_species(config.get("species"))
    min_log2fc = float(config.get("min_log2fc") or 0.25)
    min_matched_genes = int(config.get("min_matched_genes") or 2)

    if not organism:
        missing_config.append("dataset.organism")
    if catalog_path is None:
        missing_config.append("providers.marker_catalog.catalog_path")
    elif not catalog_path.exists():
        missing_config.append(f"catalog_path not found: {catalog_path}")

    entries: list[CatalogEntry] = []
    catalog_species: set[str] = set()
    if catalog_path is not None and catalog_path.exists():
        try:
            entries = read_catalog(catalog_path)
            catalog_species = {normalize_species(entry.species) for entry in entries if entry.species}
        except Exception as exc:
            errors.append(str(exc))

    expected_species = configured_species or (next(iter(catalog_species)) if len(catalog_species) == 1 else "")
    if catalog_species and len(catalog_species) > 1:
        missing_config.append("catalog contains multiple species; set providers.marker_catalog.species and split catalogs by organism")
    if configured_species and catalog_species and configured_species not in catalog_species:
        missing_config.append("providers.marker_catalog.species does not match catalog species")
    if organism and expected_species and organism != expected_species:
        missing_config.append(
            f"dataset organism '{dataset.get('organism')}' does not match marker catalog species '{expected_species}'"
        )

    marker_path = results_dir / "providers" / "marker_based" / "tables" / "differential_markers.csv"
    marker_rows: list[dict[str, str]] = []
    if not bool(config.get("_marker_based_enabled", True)):
        missing_config.append("providers.marker_based must be enabled for marker_catalog")
    elif not marker_path.exists():
        missing_config.append("marker_based differential_markers.csv")
    else:
        marker_rows = read_marker_rows(marker_path)

    matches: list[dict[str, Any]] = []
    cluster_predictions: list[dict[str, Any]] = []
    if not missing_config and not errors:
        matches = score_catalog(marker_rows, entries, min_log2fc=min_log2fc, min_matched_genes=min_matched_genes)
        cluster_predictions = cluster_predictions_from_matches(matches)
        if not matches:
            warnings.append("Marker catalog was compatible, but no catalog entries matched the informative cluster markers.")

    write_csv(tables_dir / "catalog_matches.csv", matches, MATCH_FIELDS)
    state = "failed" if errors else "needs_config" if missing_config else "completed_with_warnings" if warnings else "completed"
    payload = {
        "schema_version": 1,
        "provider": {
            "id": "marker_catalog",
            "name": "Marker catalog scoring",
            "group": "marker_based",
            "version": "0.1.0",
            "environment": {
                "manager": "pixi",
                "lockfile": "pixi.lock",
                "command": "python providers/marker_catalog/run.py",
            },
        },
        "input": {
            "h5ad": str(input_h5ad),
            "input_source_template": dataset.get("input_source_template") or None,
            "organism": dataset.get("organism") or None,
            "tissue": dataset.get("tissue") or None,
            "cluster_key": cluster_key,
            "gene_id_type": dataset.get("gene_id_type") or None,
            "catalog_path": str(catalog_path) if catalog_path is not None else None,
            "catalog_sha256": sha256_file(catalog_path) if catalog_path is not None and catalog_path.exists() else None,
            "catalog_species": expected_species or None,
            "catalog_resource_id": resource_id or None,
            "catalog_rows": len(entries),
        },
        "resources": {
            "marker_catalog": {
                "resource_id": resource_id or None,
                "kind": "local_marker_catalog",
                "path": str(catalog_path) if catalog_path is not None else None,
                "sha256": sha256_file(catalog_path) if catalog_path is not None and catalog_path.exists() else None,
                "species": expected_species or None,
                "cache_env_var": "SCRNA_ANNOTATE_CACHE_DIR",
                "cache_dir": catalog_cache_dir(),
            }
        },
        "status": {
            "state": state,
            "missing_config": missing_config,
            "warnings": warnings,
            "errors": errors,
            "started_at": started_at,
            "completed_at": utc_now(),
        },
        "aggregation": None,
        "cluster_predictions": cluster_predictions,
        "cell_predictions": [],
        "artifacts": {
            "reports": [],
            "tables": [
                {"type": "table", "path": relative_to(tables_dir / "catalog_matches.csv", template_dir), "description": "Marker catalog matches by cluster", "format": "csv"}
            ],
            "figures": [],
            "logs": [],
        },
        "methods": [
            {
                "step": "Marker catalog scoring",
                "tool": "local marker catalog overlap",
                "parameters": {
                    "catalog_path": str(catalog_path) if catalog_path is not None else None,
                    "species": expected_species or None,
                    "min_log2fc": min_log2fc,
                    "min_matched_genes": min_matched_genes,
                },
                "interpretation": "Organism-aware marker catalog evidence for review, not classifier probability or final annotation.",
            }
        ],
        "enabled": True,
    }
    write_json(provider_dir / "annotation_result.json", payload)
    return payload


def resolve_catalog_path(template_dir: Path, value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (template_dir / path).resolve()
    return path


def catalog_cache_dir() -> str:
    return os.environ.get("SCRNA_ANNOTATE_CACHE_DIR", str(Path("~/.cache/izkf_pack/scrna_annotate/catalogs").expanduser()))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_catalog(path: Path) -> list[CatalogEntry]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        missing = [field for field in CATALOG_REQUIRED_FIELDS if field not in fieldnames]
        if missing:
            raise ValueError(f"marker catalog is missing required columns: {', '.join(missing)}")
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
        raise ValueError("marker catalog did not contain any usable cell_type/gene_symbol rows")
    return entries


def read_marker_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def score_catalog(
    marker_rows: list[dict[str, str]],
    entries: list[CatalogEntry],
    *,
    min_log2fc: float,
    min_matched_genes: int,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    markers_by_cluster: dict[str, set[str]] = defaultdict(set)
    for row in marker_rows:
        if is_informative_marker_row(row, min_log2fc=min_log2fc):
            markers_by_cluster[str(row.get("cluster_id", ""))].add(normalize_gene(row.get("gene", "")))

    catalog_groups: dict[tuple[str, str, str, str, str, str, str], set[str]] = defaultdict(set)
    for entry in entries:
        key = (entry.cell_type, entry.catalog_id, entry.species, entry.organism_id, entry.tissue, entry.stage, entry.source)
        catalog_groups[key].add(normalize_gene(entry.gene_symbol))

    rows: list[dict[str, Any]] = []
    for cluster_id, marker_genes in sorted(markers_by_cluster.items(), key=lambda item: item[0]):
        scored: list[dict[str, Any]] = []
        for (cell_type, catalog_id, species, organism_id, tissue, stage, source), catalog_genes in catalog_groups.items():
            matched = sorted(marker_genes & catalog_genes)
            if len(matched) < min_matched_genes:
                continue
            missing = sorted(catalog_genes - marker_genes)
            coverage = len(matched) / len(catalog_genes) if catalog_genes else 0.0
            jaccard = len(matched) / len(marker_genes | catalog_genes) if marker_genes or catalog_genes else 0.0
            score = (0.65 * coverage) + (0.35 * jaccard)
            citation = first_citation(entries, cell_type=cell_type, catalog_id=catalog_id, source=source)
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
                    "citation": citation,
                    "n_matched": len(matched),
                    "n_catalog_genes": len(catalog_genes),
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


def cluster_predictions_from_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in matches:
        by_cluster[str(row["cluster_id"])].append(row)
    predictions: list[dict[str, Any]] = []
    for cluster_id, rows in sorted(by_cluster.items(), key=lambda item: item[0]):
        candidates = [
            {
                "label_raw": row["cell_type"],
                "label_normalized": row["cell_type"],
                "ontology_id": None,
                "rank": int(row["rank"]),
                "provider_score": float(row["score"]),
                "provider_score_name": "marker_catalog_overlap",
                "confidence_bucket": row["confidence_bucket"],
                "evidence": {
                    "catalog_id": row["catalog_id"],
                    "species": row["species"],
                    "organism_id": row["organism_id"],
                    "tissue": row["tissue"],
                    "stage": row["stage"],
                    "source": row["source"],
                    "citation": row["citation"],
                    "n_matched": row["n_matched"],
                    "n_catalog_genes": row["n_catalog_genes"],
                    "coverage": row["coverage"],
                    "jaccard": row["jaccard"],
                    "matched_genes": split_gene_list(row["matched_genes"]),
                    "missing_genes": split_gene_list(row["missing_genes"]),
                },
            }
            for row in rows
        ]
        top = candidates[0] if candidates else None
        predictions.append(
            {
                "cluster_id": cluster_id,
                "top_label": top["label_raw"] if top else None,
                "confidence_bucket": top["confidence_bucket"] if top else "unknown",
                "candidates": candidates,
            }
        )
    return predictions


def first_citation(entries: list[CatalogEntry], *, cell_type: str, catalog_id: str, source: str) -> str:
    for entry in entries:
        if entry.cell_type == cell_type and entry.catalog_id == catalog_id and entry.source == source and entry.citation:
            return entry.citation
    return ""


def is_informative_marker_row(row: dict[str, str], *, min_log2fc: float) -> bool:
    pval_adj = parse_float(row.get("pval_adj"), default=1.0)
    log2fc = parse_float(row.get("log2fc"), default=0.0)
    return pval_adj < 0.05 and log2fc >= min_log2fc


def parse_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def confidence_bucket(score: float, n_matched: int) -> str:
    if score >= 0.28 and n_matched >= 3:
        return "high"
    if score >= 0.14 and n_matched >= 2:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def normalize_species(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    aliases = {
        "danio rerio": "zebrafish",
        "dre": "zebrafish",
        "ncbitaxon:7955": "zebrafish",
        "homo sapiens": "human",
        "ncbitaxon:9606": "human",
        "mus musculus": "mouse",
        "ncbitaxon:10090": "mouse",
    }
    return aliases.get(text, text)


def normalize_gene(value: Any) -> str:
    return str(value or "").strip().lower()


def split_gene_list(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]
