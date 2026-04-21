from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy import sparse


RAW_H5AD_ERROR = (
    "H5AD input must provide raw counts for preprocessing. Supply a raw-count object or "
    "store raw counts in `adata.layers['counts']` before running scrna_prep."
)
TEXT_MISSING_VALUES = {"", "nan", "none", "na", "n/a", "<na>"}
GENE_SYMBOL_COLUMNS = (
    "gene_symbols",
    "gene_symbol",
    "gene_name",
    "feature_name",
    "feature_names",
    "symbol",
    "gene",
    "gene_short_name",
)
ENSEMBL_LIKE_RE = re.compile(r"^ENS[A-Z0-9]*[GPT]\d+(?:\.\d+)?$")


def sparse_copy(x):
    return x.copy() if sparse.issparse(x) else np.array(x, copy=True)


def normalize_text_series(values, *, fallback: str = "unknown") -> pd.Series:
    series = values.copy() if isinstance(values, pd.Series) else pd.Series(values)
    series = series.astype("object")
    series = series.where(series.notna(), None)
    series = series.map(lambda value: str(value).strip() if value is not None else "")
    series = series.mask(series.str.lower().isin(TEXT_MISSING_VALUES), "")
    return series.where(series != "", fallback)


def resolve_qc_feature_names(var: pd.DataFrame, var_names) -> pd.Index:
    fallback = pd.Index(var_names.astype(str) if isinstance(var_names, pd.Index) else pd.Index(var_names).astype(str))
    for column in GENE_SYMBOL_COLUMNS:
        if column not in var.columns:
            continue
        values = normalize_text_series(var[column], fallback="")
        if (values != "").any():
            combined = values.where(values != "", fallback)
            return pd.Index(combined.astype(str), dtype="object")
    return fallback


def looks_like_gene_ids(values, *, max_values: int = 500) -> bool:
    index = values if isinstance(values, pd.Index) else pd.Index(values)
    sample = [str(value).strip() for value in index[:max_values] if str(value).strip()]
    if not sample:
        return False
    matches = sum(bool(ENSEMBL_LIKE_RE.match(value)) for value in sample)
    return matches / len(sample) >= 0.5


def matrix_looks_like_raw_counts(x, *, max_values: int = 200000) -> bool:
    if sparse.issparse(x):
        values = np.asarray(x.data)
    else:
        values = np.asarray(x)

    if values.size == 0:
        return True

    values = values.reshape(-1)
    if values.size > max_values:
        values = values[:max_values]
    if not np.isfinite(values).all():
        return False
    if (values < 0).any():
        return False
    return np.allclose(values, np.round(values), atol=1e-8)


def ensure_preprocessing_counts_matrix(adata, *, input_format: str):
    fmt = str(input_format).strip().lower()
    if fmt == "h5ad":
        if "counts" in adata.layers:
            adata.X = sparse_copy(adata.layers["counts"])
            return adata
        if not matrix_looks_like_raw_counts(adata.X):
            raise RuntimeError(RAW_H5AD_ERROR)
        adata.layers["counts"] = sparse_copy(adata.X)
        return adata

    if "counts" not in adata.layers:
        adata.layers["counts"] = sparse_copy(adata.X)
    return adata
