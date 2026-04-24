from __future__ import annotations

from pathlib import Path

import pandas as pd
import scanpy as sc
import yaml


TEXT_MISSING_VALUES = {"", "nan", "none", "na", "n/a", "<na>"}
GENE_SYMBOL_COLUMNS = ("gene_symbols", "gene_symbol", "gene_name", "symbol", "feature_name")


def normalize_text_series(values, *, fallback: str = "unknown") -> pd.Series:
    series = values.copy() if isinstance(values, pd.Series) else pd.Series(values)
    series = series.astype("object")
    series = series.where(series.notna(), None)
    series = series.map(lambda value: str(value).strip() if value is not None else "")
    series = series.mask(series.str.lower().isin(TEXT_MISSING_VALUES), "")
    return series.where(series != "", fallback)


def load_adata(path: str):
    input_path = Path(path).expanduser().resolve()
    if not input_path.exists():
        raise RuntimeError(f"Input H5AD not found: {input_path}")
    return sc.read_h5ad(input_path), input_path


def require_obs_column(adata, key: str, *, allow_single_category: bool = True) -> pd.Series:
    if key not in adata.obs.columns:
        raise RuntimeError(f"Required obs column not found: {key}")
    values = normalize_text_series(adata.obs[key], fallback="")
    if not (values != "").any():
        raise RuntimeError(f"Obs column '{key}' does not contain any non-empty values.")
    if not allow_single_category and values[values != ""].nunique() < 2:
        raise RuntimeError(f"Obs column '{key}' must contain at least two distinct non-empty categories.")
    adata.obs[key] = values.where(values != "", "unknown")
    return adata.obs[key]


def resolve_optional_obs_column(adata, key: str, *, fallback: str = "unknown") -> pd.Series:
    if key not in adata.obs.columns:
        return pd.Series([fallback] * adata.n_obs, index=adata.obs_names, dtype="object")
    return normalize_text_series(adata.obs[key], fallback=fallback)


def resolve_sample_display(adata, sample_id_key: str, sample_label_key: str) -> pd.Series:
    sample_ids = resolve_optional_obs_column(adata, sample_id_key, fallback="unknown")
    sample_labels = resolve_optional_obs_column(adata, sample_label_key, fallback="")
    return sample_labels.where(sample_labels != "", sample_ids)


def looks_like_gene_ids(var_names) -> bool:
    probe = [str(item) for item in list(var_names[: min(20, len(var_names))])]
    if not probe:
        return False
    return sum(item.startswith(("ENSG", "ENSMUSG", "ENSRNOG", "ENSDARG", "ENSSSCG")) for item in probe) >= max(1, len(probe) // 2)


def resolve_gene_symbols(var: pd.DataFrame, var_names) -> pd.Index:
    if not looks_like_gene_ids(var_names):
        return pd.Index(var_names)
    for col in GENE_SYMBOL_COLUMNS:
        if col not in var.columns:
            continue
        series = normalize_text_series(var[col], fallback="")
        if (series != "").any():
            return pd.Index(series.where(series != "", pd.Index(var_names).astype(str)))
    raise RuntimeError(
        "The input appears to use feature IDs, but no recognized gene-symbol column was found in adata.var."
    )


def load_marker_sets(path: str) -> dict[str, list[str]]:
    raw_path = str(path).strip()
    if not raw_path:
        return {}
    marker_path = Path(raw_path).expanduser().resolve()
    if not marker_path.exists():
        raise RuntimeError(f"Marker file not found: {marker_path}")
    payload = yaml.safe_load(marker_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Marker file must be a mapping from label names to marker gene lists.")
    out: dict[str, list[str]] = {}
    for key, value in payload.items():
        label = str(key).strip()
        if not label:
            continue
        genes: list[str] = []
        if isinstance(value, list):
            genes = [str(item).strip() for item in value if str(item).strip()]
        elif isinstance(value, dict) and isinstance(value.get("markers"), list):
            genes = [str(item).strip() for item in value["markers"] if str(item).strip()]
        else:
            raise RuntimeError(f"Marker entry '{label}' must be a list of genes or a mapping with a 'markers' list.")
        if genes:
            out[label] = genes
    return out
