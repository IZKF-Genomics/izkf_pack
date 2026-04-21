from __future__ import annotations

import pandas as pd
import scanpy as sc


def score_marker_sets(adata, marker_sets: dict[str, list[str]], *, cluster_key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not marker_sets:
        return pd.DataFrame(columns=["cluster", "marker_suggested_label", "marker_score"]), pd.DataFrame(columns=["cluster", "label", "marker_score"])

    scored = adata.copy()
    score_columns: list[str] = []
    for label, genes in marker_sets.items():
        overlap = [gene for gene in genes if gene in scored.var_names]
        if not overlap:
            continue
        column = f"marker_score__{label}"
        sc.tl.score_genes(scored, gene_list=overlap, score_name=column, use_raw=False)
        score_columns.append(column)

    if not score_columns:
        return pd.DataFrame(columns=["cluster", "marker_suggested_label", "marker_score"]), pd.DataFrame(columns=["cluster", "label", "marker_score"])

    cluster_scores = (
        scored.obs[[cluster_key, *score_columns]]
        .groupby(cluster_key, dropna=False)
        .mean()
        .reset_index()
        .rename(columns={cluster_key: "cluster"})
    )
    long_scores = cluster_scores.melt(id_vars="cluster", var_name="label", value_name="marker_score")
    long_scores["label"] = long_scores["label"].str.removeprefix("marker_score__")
    marker_summary = (
        long_scores.sort_values(["cluster", "marker_score"], ascending=[True, False])
        .groupby("cluster", as_index=False)
        .first()
        .rename(columns={"label": "marker_suggested_label"})
    )
    return marker_summary, long_scores


def merge_marker_review(cluster_summary: pd.DataFrame, marker_summary: pd.DataFrame) -> pd.DataFrame:
    if marker_summary.empty:
        out = cluster_summary.copy()
        out["marker_suggested_label"] = ""
        out["marker_score"] = pd.NA
        return out

    out = cluster_summary.merge(marker_summary, how="left", on="cluster")
    conflict = (
        out["annotation_status"].eq("accepted")
        & out["marker_suggested_label"].fillna("").ne("")
        & out["marker_suggested_label"].ne(out["cluster_suggested_label"])
    )
    out.loc[conflict, "annotation_status"] = "review_needed_marker_conflict"
    out.loc[conflict, "cluster_suggested_label"] = out.loc[conflict, "cluster_suggested_label"]
    return out
