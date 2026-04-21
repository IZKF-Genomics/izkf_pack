from __future__ import annotations

from pathlib import Path

import pandas as pd
import scanpy as sc


TEXT_MISSING_VALUES = {"", "nan", "none", "na", "n/a", "<na>"}


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
        raise RuntimeError(f"Obs column '{key}' must contain at least two distinct non-empty categories for integration.")
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


def ensure_counts_layer(adata, *, method: str) -> str:
    if "counts" not in adata.layers:
        raise RuntimeError(f"{method} requires raw counts in adata.layers['counts'].")
    return "counts"

