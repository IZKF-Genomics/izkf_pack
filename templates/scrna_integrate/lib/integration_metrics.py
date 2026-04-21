from __future__ import annotations

import math

import igraph as ig
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.metrics import silhouette_score
from sklearn.neighbors import NearestNeighbors


def _normalized_entropy(values: pd.Series) -> float:
    counts = values.value_counts()
    if counts.empty or counts.size < 2:
        return math.nan
    probs = counts / counts.sum()
    entropy = float(-(probs * np.log2(probs)).sum())
    return entropy / math.log2(counts.size)


def neighborhood_batch_metrics(adata, *, batch_key: str, use_rep: str, n_neighbors: int) -> dict[str, float]:
    rep = adata.obsm[use_rep]
    k = min(max(2, int(n_neighbors)), adata.n_obs - 1)
    nn = NearestNeighbors(n_neighbors=k + 1)
    nn.fit(rep)
    indices = nn.kneighbors(return_distance=False)[:, 1:]
    batches = adata.obs[batch_key].astype(str).reset_index(drop=True)

    entropies = []
    same_batch = []
    for row_index, neighbors in enumerate(indices):
        neighbor_batches = batches.iloc[neighbors]
        entropies.append(_normalized_entropy(neighbor_batches))
        same_batch.append(float((neighbor_batches == batches.iloc[row_index]).mean()))

    return {
        "batch_entropy_mean": float(np.nanmean(entropies)) if entropies else math.nan,
        "same_batch_neighbor_fraction_mean": float(np.nanmean(same_batch)) if same_batch else math.nan,
    }


def label_silhouette_metric(adata, *, label_key: str, use_rep: str) -> float:
    if label_key not in adata.obs.columns:
        return math.nan
    labels = adata.obs[label_key].astype(str)
    valid = labels.str.strip() != ""
    labels = labels[valid]
    if labels.nunique() < 2 or labels.shape[0] < 3:
        return math.nan
    rep = adata.obsm[use_rep][valid.to_numpy()]
    return float(silhouette_score(rep, labels))


def graph_connectivity_metric(adata, *, label_key: str) -> float:
    if label_key not in adata.obs.columns or "connectivities" not in adata.obsp:
        return math.nan
    labels = adata.obs[label_key].astype(str)
    if labels.nunique() < 2:
        return math.nan
    coo = sparse.triu(adata.obsp["connectivities"], k=1).tocoo()
    graph = ig.Graph(n=adata.n_obs, edges=list(zip(coo.row.tolist(), coo.col.tolist())), directed=False)
    scores = []
    for label in sorted(labels.unique()):
        idx = np.flatnonzero((labels == label).to_numpy())
        if idx.size < 2:
            continue
        subgraph = graph.induced_subgraph(idx.tolist())
        components = subgraph.components()
        largest = max((len(component) for component in components), default=0)
        scores.append(largest / idx.size)
    return float(np.mean(scores)) if scores else math.nan


def maybe_scib_metrics(unintegrated, integrated, *, batch_key: str, label_key: str, use_rep: str) -> pd.DataFrame:
    if not label_key or label_key not in integrated.obs.columns:
        return pd.DataFrame(columns=["metric", "value", "source"])
    try:
        import scib
    except ImportError:
        return pd.DataFrame(columns=["metric", "value", "source"])

    metrics = scib.metrics.metrics_fast(unintegrated, integrated, batch_key, label_key, embed=use_rep)
    if isinstance(metrics, pd.DataFrame):
        if metrics.shape[1] == 1:
            metric_series = metrics.iloc[:, 0]
        else:
            metric_series = metrics.squeeze(axis=1)
    else:
        metric_series = metrics
    return (
        pd.DataFrame({"metric": metric_series.index.astype(str), "value": metric_series.to_numpy()})
        .assign(source="scib")
        .reset_index(drop=True)
    )


def compare_baseline_and_integrated(
    baseline,
    integrated,
    *,
    batch_key: str,
    label_key: str,
    baseline_rep: str,
    integrated_rep: str,
    n_neighbors: int,
    run_scib_metrics: bool,
) -> pd.DataFrame:
    rows = []

    baseline_batch = neighborhood_batch_metrics(baseline, batch_key=batch_key, use_rep=baseline_rep, n_neighbors=n_neighbors)
    integrated_batch = neighborhood_batch_metrics(integrated, batch_key=batch_key, use_rep=integrated_rep, n_neighbors=n_neighbors)
    for metric, value in baseline_batch.items():
        rows.append({"stage": "baseline", "metric": metric, "value": value, "source": "native"})
    for metric, value in integrated_batch.items():
        rows.append({"stage": "integrated", "metric": metric, "value": value, "source": "native"})

    if label_key and label_key in baseline.obs.columns:
        rows.append(
            {
                "stage": "baseline",
                "metric": "label_silhouette",
                "value": label_silhouette_metric(baseline, label_key=label_key, use_rep=baseline_rep),
                "source": "native",
            }
        )
        rows.append(
            {
                "stage": "integrated",
                "metric": "label_silhouette",
                "value": label_silhouette_metric(integrated, label_key=label_key, use_rep=integrated_rep),
                "source": "native",
            }
        )
        rows.append(
            {
                "stage": "baseline",
                "metric": "graph_connectivity",
                "value": graph_connectivity_metric(baseline, label_key=label_key),
                "source": "native",
            }
        )
        rows.append(
            {
                "stage": "integrated",
                "metric": "graph_connectivity",
                "value": graph_connectivity_metric(integrated, label_key=label_key),
                "source": "native",
            }
        )

    out = pd.DataFrame(rows)
    if run_scib_metrics:
        scib_df = maybe_scib_metrics(
            baseline,
            integrated,
            batch_key=batch_key,
            label_key=label_key,
            use_rep=integrated_rep,
        )
        if not scib_df.empty:
            scib_df.insert(0, "stage", "integrated")
            out = pd.concat([out, scib_df], ignore_index=True)
    return out
