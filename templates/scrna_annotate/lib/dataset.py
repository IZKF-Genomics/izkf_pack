from __future__ import annotations

from pathlib import Path
from typing import Any


def profile_dataset(path: Path, params: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    profile: dict[str, Any] = {
        "path": str(path),
        "file_exists": path.exists(),
        "readable": False,
        "n_cells": None,
        "n_genes": None,
        "obs_columns": [],
        "var_columns": [],
        "layers": [],
        "obsm_keys": [],
        "has_umap": False,
        "cluster_key": params.get("cluster_key", ""),
        "cluster_key_exists": False,
        "cluster_count": None,
        "cluster_sizes": {},
        "gene_id_guess": "unknown",
        "warnings": warnings,
    }
    if not path.exists():
        warnings.append(f"Dataset file not found: {path}")
        return profile

    try:
        import anndata as ad

        adata = ad.read_h5ad(path, backed="r")
    except Exception as exc:
        warnings.append(f"Could not read h5ad: {exc}")
        return profile

    cluster_key = str(params.get("cluster_key") or "")
    profile.update(
        {
            "readable": True,
            "n_cells": int(adata.n_obs),
            "n_genes": int(adata.n_vars),
            "obs_columns": list(map(str, adata.obs.columns)),
            "var_columns": list(map(str, adata.var.columns)),
            "layers": list(map(str, adata.layers.keys())),
            "obsm_keys": list(map(str, adata.obsm.keys())),
            "has_umap": "X_umap" in adata.obsm,
            "gene_id_guess": infer_gene_id_type([str(name) for name in list(adata.var_names[:1000])]),
        }
    )
    if cluster_key and cluster_key in adata.obs:
        counts = adata.obs[cluster_key].dropna().astype(str).value_counts().sort_index()
        profile["cluster_key_exists"] = True
        profile["cluster_count"] = int(len(counts))
        profile["cluster_sizes"] = {str(index): int(value) for index, value in counts.items()}
    elif cluster_key:
        warnings.append(f"cluster_key '{cluster_key}' was not found in .obs")
    else:
        warnings.append("No cluster_key was provided.")
    if params.get("tissue") in {"", None}:
        warnings.append("Tissue is not set; marker interpretation should be treated as context-light.")
    return profile


def infer_gene_id_type(names: list[str]) -> str:
    if not names:
        return "unknown"
    ensembl = sum(1 for name in names if name.upper().startswith(("ENSG", "ENSMUSG")))
    symbols = sum(1 for name in names if name and not name.upper().startswith(("ENSG", "ENSMUSG")))
    if ensembl and symbols:
        return "mixed"
    if ensembl:
        return "ensembl"
    if symbols:
        return "gene_symbols"
    return "unknown"
