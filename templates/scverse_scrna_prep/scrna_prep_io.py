from __future__ import annotations

import numpy as np
from scipy import sparse


RAW_H5AD_ERROR = (
    "H5AD input must provide raw counts for preprocessing. Supply a raw-count object or "
    "store raw counts in `adata.layers['counts']` before running scverse_scrna_prep."
)


def sparse_copy(x):
    return x.copy() if sparse.issparse(x) else np.array(x, copy=True)


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
