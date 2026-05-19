from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


PROVIDER_GROUPS = {
    "marker_based": "marker_based",
    "marker_catalog": "marker_based",
    "celltypist": "reference_based",
    "singler": "reference_based",
    "manual_curated": "manual_curated",
    "mock_provider": "mock",
    "scgpt": "foundation_model",
    "sctab": "foundation_model",
}


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def env(name: str) -> str:
    return os.environ.get(name, "")


def load_dataset_params(config_dir: Path) -> dict[str, Any]:
    config = read_toml(config_dir / "dataset.toml")
    dataset = dict(config.get("dataset", {}))
    validation = dict(dataset.get("validation", {}))
    dataset.pop("validation", None)
    params = {
        "input_h5ad": dataset.get("input_h5ad", ""),
        "input_source_template": dataset.get("input_source_template", ""),
        "organism": dataset.get("organism", ""),
        "tissue": dataset.get("tissue", ""),
        "cluster_key": dataset.get("cluster_key", "leiden"),
        "sample_key": dataset.get("sample_key", "sample_id"),
        "batch_key": dataset.get("batch_key", "batch"),
        "condition_key": dataset.get("condition_key", "condition"),
        "gene_id_type": dataset.get("gene_id_type", "gene_symbols"),
        "expression_layer": dataset.get("expression_layer", "X"),
        "raw_layer": dataset.get("raw_layer", "counts"),
        "validation": validation,
    }
    overrides = {
        "input_h5ad": env("INPUT_H5AD"),
        "input_source_template": env("INPUT_SOURCE_TEMPLATE"),
        "organism": env("ORGANISM"),
        "tissue": env("TISSUE"),
        "cluster_key": env("CLUSTER_KEY"),
        "sample_key": env("SAMPLE_ID_KEY") or env("SAMPLE_KEY"),
        "batch_key": env("BATCH_KEY"),
        "condition_key": env("CONDITION_KEY"),
        "gene_id_type": env("GENE_ID_TYPE"),
        "expression_layer": env("EXPRESSION_LAYER"),
    }
    for key, value in overrides.items():
        if value:
            params[key] = value
    return params


def load_provider_params(config_dir: Path) -> dict[str, Any]:
    config = read_toml(config_dir / "providers.toml")
    providers = dict(config.get("providers", {}))
    marker = dict(providers.get("marker_based", {}))
    marker_catalog = dict(providers.get("marker_catalog", {}))
    if env("MARKER_BASED_ENABLED"):
        marker["enabled"] = parse_bool(env("MARKER_BASED_ENABLED"))
    if env("TOP_N_MARKERS"):
        marker["top_n_markers"] = int(env("TOP_N_MARKERS"))
    if env("MIN_LOG2FC"):
        marker["min_log2fc"] = float(env("MIN_LOG2FC"))
    if env("EXPRESSION_LAYER"):
        marker["expression_layer"] = env("EXPRESSION_LAYER")
    providers["marker_based"] = marker
    if env("MARKER_CATALOG_ENABLED"):
        marker_catalog["enabled"] = parse_bool(env("MARKER_CATALOG_ENABLED"))
    if env("MARKER_CATALOG_RESOURCE_ID"):
        marker_catalog["resource_id"] = env("MARKER_CATALOG_RESOURCE_ID")
    if env("MARKER_CATALOG_PATH"):
        marker_catalog["catalog_path"] = env("MARKER_CATALOG_PATH")
    if env("MARKER_CATALOG_SPECIES"):
        marker_catalog["species"] = env("MARKER_CATALOG_SPECIES")
    if env("MARKER_CATALOG_MIN_LOG2FC"):
        marker_catalog["min_log2fc"] = float(env("MARKER_CATALOG_MIN_LOG2FC"))
    if env("MARKER_CATALOG_MIN_MATCHED_GENES"):
        marker_catalog["min_matched_genes"] = int(env("MARKER_CATALOG_MIN_MATCHED_GENES"))
    providers["marker_catalog"] = marker_catalog
    return {
        "preset": dict(config.get("preset", {})),
        "providers": providers,
    }


def resolve_input_h5ad(template_dir: Path, params: dict[str, Any]) -> Path:
    value = str(params.get("input_h5ad") or "").strip()
    if not value:
        raise SystemExit("Set INPUT_H5AD to the prepared .h5ad file before running scrna_annotate.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (template_dir / path).resolve()
    return path
