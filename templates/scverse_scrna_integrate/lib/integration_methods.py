from __future__ import annotations

import math

import numpy as np
import scanpy as sc

try:
    import scanpy.external as sce
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("scanpy.external is required for integration methods") from exc


ALLOWED_METHODS = {"scvi", "scanvi", "harmony", "bbknn", "scanorama"}


def ensure_hvg_subset(adata, *, use_hvgs_only: bool, n_top_hvgs: int):
    out = adata.copy()
    if "highly_variable" not in out.var.columns or not out.var["highly_variable"].any():
        sc.pp.highly_variable_genes(out, n_top_genes=int(n_top_hvgs), flavor="seurat")
    if use_hvgs_only and out.var["highly_variable"].any():
        return out[:, out.var["highly_variable"].to_numpy()].copy()
    return out


def run_baseline_embedding(adata, *, n_pcs: int, n_neighbors: int, umap_min_dist: float, cluster_resolution: float, random_state: int):
    baseline = adata.copy()
    max_pcs = min(max(2, int(n_pcs)), baseline.n_obs - 1, baseline.n_vars - 1)
    sc.tl.pca(baseline, n_comps=max_pcs, svd_solver="arpack")
    sc.pp.neighbors(baseline, n_neighbors=min(max(2, int(n_neighbors)), baseline.n_obs - 1), n_pcs=max_pcs)
    sc.tl.umap(baseline, min_dist=float(umap_min_dist), random_state=int(random_state))
    sc.tl.leiden(baseline, resolution=float(cluster_resolution), key_added="baseline_leiden")
    baseline.uns["baseline_embedding_key"] = "X_pca"
    baseline.uns["baseline_n_pcs"] = int(max_pcs)
    return baseline


def run_classical_integration(
    adata,
    *,
    method: str,
    batch_key: str,
    n_pcs: int,
    n_neighbors: int,
    umap_min_dist: float,
    cluster_resolution: float,
    random_state: int,
    harmony_theta: float,
    harmony_lambda: float,
    harmony_max_iter: int,
    bbknn_neighbors_within_batch: int,
    bbknn_trim: int,
):
    integrated = adata.copy()
    max_pcs = min(max(2, int(n_pcs)), integrated.n_obs - 1, integrated.n_vars - 1)
    sc.tl.pca(integrated, n_comps=max_pcs, svd_solver="arpack")

    if method == "harmony":
        sce.pp.harmony_integrate(
            integrated,
            key=batch_key,
            basis="X_pca",
            adjusted_basis="X_pca_harmony",
            theta=float(harmony_theta),
            lambda_=float(harmony_lambda),
            max_iter_harmony=int(harmony_max_iter),
        )
        use_rep = "X_pca_harmony"
    elif method == "bbknn":
        bbknn_kwargs = {
            "batch_key": batch_key,
            "n_pcs": max_pcs,
            "neighbors_within_batch": int(bbknn_neighbors_within_batch),
        }
        if int(bbknn_trim) > 0:
            bbknn_kwargs["trim"] = int(bbknn_trim)
        sce.pp.bbknn(integrated, **bbknn_kwargs)
        use_rep = "X_pca"
    else:
        sce.pp.scanorama_integrate(
            integrated,
            key=batch_key,
            basis="X_pca",
            adjusted_basis="X_scanorama",
        )
        use_rep = "X_scanorama"

    if method != "bbknn":
        sc.pp.neighbors(integrated, use_rep=use_rep, n_neighbors=min(max(2, int(n_neighbors)), integrated.n_obs - 1))
    sc.tl.umap(integrated, min_dist=float(umap_min_dist), random_state=int(random_state))
    sc.tl.leiden(integrated, resolution=float(cluster_resolution))
    integrated.uns["integration_embedding_key"] = use_rep
    integrated.uns["integration_n_pcs"] = int(max_pcs)
    return integrated


def run_scvi_integration(
    adata,
    *,
    method: str,
    batch_key: str,
    counts_layer: str,
    scanvi_label_key: str,
    scanvi_unlabeled_category: str,
    scvi_latent_dim: int,
    scvi_max_epochs: int,
    scvi_gene_likelihood: str,
    scvi_accelerator: str,
    scvi_devices: int,
    n_neighbors: int,
    umap_min_dist: float,
    cluster_resolution: float,
    random_state: int,
):
    try:
        import scvi
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("scvi-tools is required for scvi and scanvi integration methods") from exc

    scvi.settings.seed = int(random_state)
    model_adata = adata.copy()
    setup_kwargs = {"batch_key": batch_key, "layer": counts_layer}
    if method == "scanvi":
        if scanvi_label_key not in model_adata.obs.columns:
            raise RuntimeError(f"scanvi_label_key not found in obs: {scanvi_label_key}")
        labels = model_adata.obs[scanvi_label_key].astype("object")
        labels = labels.where(labels.notna(), scanvi_unlabeled_category)
        labels = labels.astype(str).str.strip().replace({"": scanvi_unlabeled_category, "nan": scanvi_unlabeled_category, "None": scanvi_unlabeled_category})
        model_adata.obs[scanvi_label_key] = labels.astype("category")
        setup_kwargs["labels_key"] = scanvi_label_key

    scvi.model.SCVI.setup_anndata(model_adata, **setup_kwargs)
    latent_dim = min(max(2, int(scvi_latent_dim)), model_adata.n_obs - 1, model_adata.n_vars)
    if latent_dim < 2:
        raise RuntimeError("Need at least 2 latent dimensions for scVI/scANVI.")

    scvi_model = scvi.model.SCVI(
        model_adata,
        n_latent=latent_dim,
        gene_likelihood=str(scvi_gene_likelihood).strip().lower() or "zinb",
    )
    scvi_model.train(
        max_epochs=int(scvi_max_epochs),
        accelerator=str(scvi_accelerator).strip() or "auto",
        devices=max(1, int(scvi_devices)),
    )

    if method == "scanvi":
        scanvi_model = scvi.model.SCANVI.from_scvi_model(
            scvi_model,
            labels_key=scanvi_label_key,
            unlabeled_category=scanvi_unlabeled_category,
        )
        scanvi_model.train(
            max_epochs=int(scvi_max_epochs),
            accelerator=str(scvi_accelerator).strip() or "auto",
            devices=max(1, int(scvi_devices)),
        )
        model_adata.obsm["X_scanvi"] = scanvi_model.get_latent_representation()
        use_rep = "X_scanvi"
    else:
        model_adata.obsm["X_scvi"] = scvi_model.get_latent_representation()
        use_rep = "X_scvi"

    sc.pp.neighbors(model_adata, use_rep=use_rep, n_neighbors=min(max(2, int(n_neighbors)), model_adata.n_obs - 1))
    sc.tl.umap(model_adata, min_dist=float(umap_min_dist), random_state=int(random_state))
    sc.tl.leiden(model_adata, resolution=float(cluster_resolution))
    model_adata.uns["integration_embedding_key"] = use_rep
    model_adata.uns["integration_n_pcs"] = None
    model_adata.uns["scvi_latent_dim"] = int(latent_dim)
    return model_adata

