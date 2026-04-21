from __future__ import annotations

import numpy as np
import pandas as pd
import scanpy as sc

from annotation_io import normalize_text_series, resolve_gene_symbols


def _matrix_looks_log1p_normalized(adata) -> bool:
    if adata.n_obs == 0 or adata.n_vars == 0:
        return False
    sample = adata.X[: min(1000, adata.n_obs)]
    if hasattr(sample, "toarray"):
        sample = sample.toarray()
    sample = np.asarray(sample, dtype=float)
    if sample.size == 0:
        return False
    if np.nanmin(sample) < 0:
        return False
    return np.nanmax(sample) <= 12.0


def prepare_celltypist_adata(adata):
    prepared = adata.copy()
    prepared.var_names = resolve_gene_symbols(prepared.var, prepared.var_names)
    prepared.var_names_make_unique()

    if _matrix_looks_log1p_normalized(prepared):
        return prepared

    if "counts" in prepared.layers:
        prepared.X = prepared.layers["counts"].copy()
    sc.pp.normalize_total(prepared, target_sum=1e4)
    sc.pp.log1p(prepared)
    return prepared


def run_celltypist_annotation(
    adata,
    *,
    model,
    mode: str,
    p_thres: float,
    use_gpu: bool,
    predicted_label_key: str,
):
    try:
        import celltypist
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("celltypist is required for scverse_scrna_annotate.") from exc

    prepared = prepare_celltypist_adata(adata)
    predictions = celltypist.annotate(
        prepared,
        model=model,
        mode=str(mode).replace("_", " "),
        p_thres=float(p_thres),
        majority_voting=False,
        use_GPU=bool(use_gpu),
    )

    labels = predictions.predicted_labels.copy()
    probabilities = predictions.probability_matrix.copy()
    predicted_col = "predicted_labels" if "predicted_labels" in labels.columns else labels.columns[0]
    label_series = normalize_text_series(labels[predicted_col], fallback="Unknown")
    conf_series = probabilities.max(axis=1).astype(float)

    out = pd.DataFrame(
        {
            predicted_label_key: label_series.to_numpy(),
            "predicted_confidence": conf_series.reindex(prepared.obs_names).to_numpy(),
        },
        index=prepared.obs_names,
    )
    return out, probabilities


def summarize_cluster_predictions(
    obs: pd.DataFrame,
    *,
    cluster_key: str,
    predicted_label_key: str,
    confidence_key: str,
    min_fraction: float,
    confidence_threshold: float,
    unknown_label: str,
    top_n: int,
):
    rows: list[dict[str, object]] = []
    top_label_rows: list[dict[str, object]] = []

    grouped = obs.groupby(cluster_key, dropna=False)
    for cluster, group in grouped:
        label_counts = (
            group[predicted_label_key]
            .astype(str)
            .value_counts(dropna=False)
            .rename_axis("predicted_label")
            .reset_index(name="n_cells")
        )
        label_counts["fraction"] = label_counts["n_cells"] / max(1, len(group))
        label_counts["cluster"] = cluster
        top_label_rows.extend(label_counts.head(int(top_n)).to_dict(orient="records"))

        top_row = label_counts.iloc[0]
        mean_confidence = float(group[confidence_key].mean())
        suggested = str(top_row["predicted_label"])
        status = "accepted"
        if float(top_row["fraction"]) < float(min_fraction) or mean_confidence < float(confidence_threshold):
            suggested = str(unknown_label)
            status = "review_needed"
        rows.append(
            {
                "cluster": cluster,
                "n_cells": int(len(group)),
                "top_predicted_label": str(top_row["predicted_label"]),
                "top_label_count": int(top_row["n_cells"]),
                "top_label_fraction": float(top_row["fraction"]),
                "mean_predicted_confidence": mean_confidence,
                "cluster_suggested_label": suggested,
                "annotation_status": status,
            }
        )

    cluster_summary = pd.DataFrame(rows)
    top_labels = pd.DataFrame(top_label_rows)
    return cluster_summary, top_labels


def apply_cluster_suggestions(
    obs: pd.DataFrame,
    cluster_summary: pd.DataFrame,
    *,
    cluster_key: str,
    final_label_key: str,
    unknown_label: str,
):
    annotated = obs.copy()
    merge_cols = ["cluster", "cluster_suggested_label", "annotation_status"]
    merged = annotated.merge(cluster_summary[merge_cols], how="left", left_on=cluster_key, right_on="cluster")
    merged[final_label_key] = merged["cluster_suggested_label"].fillna(str(unknown_label))
    merged.loc[merged["annotation_status"] != "accepted", final_label_key] = str(unknown_label)
    return merged.drop(columns=["cluster"])
