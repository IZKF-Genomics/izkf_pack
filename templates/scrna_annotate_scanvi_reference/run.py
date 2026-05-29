#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import tomllib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = Path(os.environ.get("LINKAR_PROJECT_DIR", TEMPLATE_DIR.parent)).resolve()
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
TABLES_DIR = RESULTS_DIR / "tables"
CONFIG_DIR = TEMPLATE_DIR / "config"
ANNOTATED_H5AD = RESULTS_DIR / "adata.annotated.h5ad"
SCHEMA_VERSION = "izkf_annotation_result.v1"
TEMPLATE_NAME = "scrna_annotate_scanvi_reference"
PREFIX = "scrna_annotate_scanvi_reference"

CELL_FIELDS = [
    "cell_id",
    "cluster_id",
    "sample_id",
    "top_label",
    "confidence_bucket",
    "max_probability",
    "entropy",
    "review_status",
    "candidate_1",
    "candidate_1_probability",
    "candidate_2",
    "candidate_2_probability",
    "candidate_3",
    "candidate_3_probability",
]
LABEL_FIELDS = ["label", "n_cells", "fraction_cells", "mean_probability", "median_probability"]
CLUSTER_FIELDS = [
    "cluster_id",
    "n_cells",
    "top_label",
    "top_label_fraction",
    "mean_probability",
    "median_probability",
    "n_predicted_labels",
    "label_counts",
    "confidence_bucket",
    "review_status",
]
REFERENCE_FIELDS = ["field", "value"]
TRAINING_FIELDS = ["metric", "epoch", "value"]


def main() -> int:
    started_at = utc_now()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    params = load_params()
    warnings: list[str] = []
    errors: list[str] = []

    input_h5ad = resolve_input_h5ad(params)
    reference_h5ad = resolve_reference_h5ad(params)
    if not input_h5ad.exists():
        raise SystemExit(f"Input h5ad not found: {input_h5ad}")
    if not reference_h5ad.exists():
        raise SystemExit(f"Reference h5ad not found: {reference_h5ad}")

    progress(f"reading query: {input_h5ad}")
    progress(f"reading reference: {reference_h5ad}")
    import anndata as ad
    import numpy as np
    import pandas as pd
    import scanpy as sc
    import scvi

    set_scvi_seed(int(params["seed"]), scvi=scvi)
    query = ad.read_h5ad(input_h5ad)
    reference = ad.read_h5ad(reference_h5ad)
    query_original_obs_names = query.obs_names.astype(str).tolist()

    reference = filter_reference(reference, params, warnings)
    validate_reference(reference, params)
    prepare_count_layer(query, params["counts_layer"], warnings, "query")
    prepare_count_layer(reference, params["counts_layer"], warnings, "reference")
    warn_if_count_layer_suspicious(query, "_izkf_counts", warnings, "query")
    warn_if_count_layer_suspicious(reference, "_izkf_counts", warnings, "reference")

    shared_genes = harmonize_genes(query, reference)
    if len(shared_genes) < int(params["min_shared_genes"]):
        warnings.append(f"Only {len(shared_genes)} shared genes were found between query and reference; label transfer may be weak.")
    query = query[:, shared_genes].copy()
    reference = reference[:, shared_genes].copy()

    combined = build_combined_adata(query, reference, params)
    progress(f"combined cells: {combined.n_obs}; shared genes: {combined.n_vars}")

    scvi.model.SCVI.setup_anndata(combined, layer="_izkf_counts", batch_key=params["batch_key"])
    vae = scvi.model.SCVI(
        combined,
        n_latent=int(params["n_latent"]),
        n_hidden=int(params["n_hidden"]),
        n_layers=int(params["n_layers"]),
    )
    progress("training SCVI")
    vae.train(max_epochs=int(params["max_epochs_scvi"]), early_stopping=bool_param(params["early_stopping"]), accelerator=accelerator_arg(params["use_gpu"]))

    progress("training SCANVI")
    lvae = scvi.model.SCANVI.from_scvi_model(
        vae,
        labels_key=params["labels_key"],
        unlabeled_category=params["query_label_value"],
    )
    lvae.train(max_epochs=int(params["max_epochs_scanvi"]), early_stopping=bool_param(params["early_stopping"]), accelerator=accelerator_arg(params["use_gpu"]))

    progress("predicting query labels")
    predictions = lvae.predict(combined)
    probabilities = lvae.predict(combined, soft=True)
    if not isinstance(probabilities, pd.DataFrame):
        probabilities = pd.DataFrame(probabilities, index=combined.obs_names)
    probabilities.index = probabilities.index.astype(str)
    predictions = pd.Series(predictions, index=combined.obs_names.astype(str), name="prediction").astype(str)

    combined.obsm["X_scVI"] = vae.get_latent_representation(combined)
    combined.obsm["X_scANVI"] = lvae.get_latent_representation(combined)
    try:
        sc.pp.neighbors(combined, use_rep="X_scANVI")
        sc.tl.umap(combined)
    except Exception as exc:
        warnings.append(f"Could not compute X_scANVI UMAP: {exc}")

    query_mask = combined.obs[params["source_key"]].astype(str) == "query"
    query_combined = combined[query_mask].copy()
    query_probs = probabilities.loc[query_combined.obs_names.astype(str)]
    query_predictions = predictions.loc[query_combined.obs_names.astype(str)]
    cell_rows = cell_prediction_rows(query_combined, query_predictions, query_probs, params)
    label_rows = label_summary_rows(cell_rows)
    cluster_rows = cluster_summary_rows(cell_rows, params["cluster_key"])
    cluster_predictions = cluster_predictions_from_summary(cluster_rows, cell_rows, int(params["top_n_candidates"]))
    reference_rows = reference_summary_rows(
        input_h5ad=input_h5ad,
        reference_h5ad=reference_h5ad,
        query=query,
        reference=reference,
        combined=combined,
        params=params,
        scvi_version=getattr(scvi, "__version__", ""),
    )
    training_rows = training_metric_rows(vae, "scvi") + training_metric_rows(lvae, "scanvi")

    write_csv(TABLES_DIR / "scanvi_cell_predictions.csv", cell_rows, CELL_FIELDS)
    write_csv(TABLES_DIR / "scanvi_label_summary.csv", label_rows, LABEL_FIELDS)
    write_csv(TABLES_DIR / "scanvi_cluster_summary.csv", cluster_rows, CLUSTER_FIELDS)
    write_csv(TABLES_DIR / "scanvi_reference_summary.csv", reference_rows, REFERENCE_FIELDS)
    write_csv(TABLES_DIR / "scanvi_training_metrics.csv", training_rows, TRAINING_FIELDS)

    artifacts: dict[str, Any] = {
        "report_html": "results/report.html",
        "report_qmd": "results/report.qmd",
        "tables": [
            "results/tables/scanvi_cell_predictions.csv",
            "results/tables/scanvi_label_summary.csv",
            "results/tables/scanvi_cluster_summary.csv",
            "results/tables/scanvi_reference_summary.csv",
            "results/tables/scanvi_training_metrics.csv",
        ],
    }
    if bool_param(params["write_h5ad"]):
        progress("writing annotated h5ad")
        write_annotated_h5ad(
            input_h5ad=input_h5ad,
            output_h5ad=ANNOTATED_H5AD,
            cell_rows=cell_rows,
            latent=query_combined.obsm.get("X_scANVI") if bool_param(params["write_latent"]) else None,
            umap=query_combined.obsm.get("X_umap") if "X_umap" in query_combined.obsm else None,
            params=params,
        )
        artifacts["annotated_h5ad"] = "results/adata.annotated.h5ad"

    if bool_param(params["write_model"]):
        model_dir = RESULTS_DIR / "model_scanvi"
        lvae.save(str(model_dir), overwrite=True)
        artifacts["scanvi_model"] = "results/model_scanvi"

    state = "failed" if errors else "completed_with_warnings" if warnings else "completed"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "template": {"name": TEMPLATE_NAME, "version": "0.1.0"},
        "run": {
            "state": state,
            "warnings": warnings,
            "errors": errors,
            "started_at": started_at,
            "completed_at": utc_now(),
        },
        "input": {
            "h5ad": str(input_h5ad),
            "input_source_template": params.get("input_source_template") or None,
            "organism": params.get("organism") or None,
            "organism_id": params.get("organism_id") or None,
            "tissue": params.get("tissue") or None,
            "cluster_key": params.get("cluster_key") or None,
            "sample_key": params.get("sample_key") or None,
            "counts_layer": params["counts_layer"],
        },
        "method": {
            "name": "scANVI reference label transfer",
            "annotation_level": "cell",
            "parameters": {
                "reference_name": params["reference_name"],
                "reference_label_key": params["reference_label_key"],
                "reference_tissue_key": params.get("reference_tissue_key") or None,
                "reference_tissue_filter": params.get("reference_tissue_filter") or None,
                "unlabeled_category": params["query_label_value"],
                "counts_layer": params["counts_layer"],
                "batch_key": params["batch_key"],
                "n_latent": int(params["n_latent"]),
                "n_hidden": int(params["n_hidden"]),
                "n_layers": int(params["n_layers"]),
                "max_epochs_scvi": int(params["max_epochs_scvi"]),
                "max_epochs_scanvi": int(params["max_epochs_scanvi"]),
                "prediction_min_probability": float(params["prediction_min_probability"]),
            },
        },
        "methods": [
            {
                "step": "Reference/query integration",
                "tool": "scvi.model.SCVI",
                "parameters": {"layer": "_izkf_counts", "batch_key": params["batch_key"]},
            },
            {
                "step": "Reference label transfer",
                "tool": "scvi.model.SCANVI",
                "parameters": {"labels_key": params["labels_key"], "unlabeled_category": params["query_label_value"]},
                "interpretation": "Predictions are calibrated to the provided reference labels and should be reviewed when probability is low or query/reference mixing is poor.",
            },
        ],
        "resources": [
            {
                "role": "reference_h5ad",
                "id": params["reference_name"],
                "path": str(reference_h5ad),
                "sha256": sha256_file(reference_h5ad),
                "species": params.get("reference_species") or None,
                "label_key": params["reference_label_key"],
                "tissue_key": params.get("reference_tissue_key") or None,
                "tissue_filter": params.get("reference_tissue_filter") or None,
                "n_cells_after_filter": int(reference.n_obs),
                "n_labels_after_filter": int(reference.obs[params["reference_label_key"]].astype(str).nunique()),
                "n_shared_genes": int(len(shared_genes)),
            }
        ],
        "cluster_predictions": cluster_predictions,
        "cell_predictions": cell_predictions_from_rows(cell_rows, int(params["top_n_candidates"])),
        "artifacts": artifacts,
    }
    write_json(RESULTS_DIR / "annotation_result.json", payload)
    render_report()
    payload["run"]["completed_at"] = utc_now()
    write_json(RESULTS_DIR / "annotation_result.json", payload)
    progress(f"done: {RESULTS_DIR / 'report.html'}")
    return 0


def load_params() -> dict[str, Any]:
    config = read_toml(CONFIG_DIR / "dataset.toml")
    dataset = dict(config.get("dataset", {}))
    reference = dict(config.get("reference", {}))
    scanvi_cfg = dict(config.get("scanvi", {}))
    outputs = dict(config.get("outputs", {}))
    params = {
        "input_h5ad": dataset.get("input_h5ad", ""),
        "input_source_template": dataset.get("input_source_template", ""),
        "organism": dataset.get("organism", "mouse"),
        "organism_id": dataset.get("organism_id", ""),
        "tissue": dataset.get("tissue", ""),
        "cluster_key": dataset.get("cluster_key", "leiden"),
        "sample_key": dataset.get("sample_key", "sample_id"),
        "counts_layer": dataset.get("counts_layer", "counts"),
        "reference_h5ad": reference.get("reference_h5ad", ""),
        "reference_name": reference.get("reference_name", "reference"),
        "reference_label_key": reference.get("reference_label_key", "cell_type"),
        "reference_batch_key": reference.get("reference_batch_key", ""),
        "reference_sample_key": reference.get("reference_sample_key", ""),
        "reference_tissue_key": reference.get("reference_tissue_key", ""),
        "reference_tissue_filter": reference.get("reference_tissue_filter", ""),
        "reference_species": reference.get("reference_species", ""),
        "query_label_value": reference.get("query_label_value", "Unknown"),
        "batch_key": scanvi_cfg.get("batch_key", f"{PREFIX}_batch"),
        "labels_key": scanvi_cfg.get("labels_key", f"{PREFIX}_training_label"),
        "source_key": scanvi_cfg.get("source_key", f"{PREFIX}_source"),
        "n_latent": scanvi_cfg.get("n_latent", 30),
        "n_hidden": scanvi_cfg.get("n_hidden", 128),
        "n_layers": scanvi_cfg.get("n_layers", 2),
        "max_epochs_scvi": scanvi_cfg.get("max_epochs_scvi", 400),
        "max_epochs_scanvi": scanvi_cfg.get("max_epochs_scanvi", 200),
        "early_stopping": scanvi_cfg.get("early_stopping", True),
        "prediction_min_probability": scanvi_cfg.get("prediction_min_probability", 0.6),
        "top_n_candidates": scanvi_cfg.get("top_n_candidates", 3),
        "seed": scanvi_cfg.get("seed", 0),
        "use_gpu": scanvi_cfg.get("use_gpu", "auto"),
        "min_shared_genes": scanvi_cfg.get("min_shared_genes", 1000),
        "write_h5ad": outputs.get("write_h5ad", True),
        "write_latent": outputs.get("write_latent", True),
        "write_model": outputs.get("write_model", False),
    }
    overrides = {
        "input_h5ad": env("INPUT_H5AD"),
        "input_source_template": env("INPUT_SOURCE_TEMPLATE"),
        "organism": env("ORGANISM"),
        "organism_id": env("ORGANISM_ID"),
        "tissue": env("TISSUE"),
        "cluster_key": env("CLUSTER_KEY"),
        "sample_key": env("SAMPLE_ID_KEY") or env("SAMPLE_KEY"),
        "counts_layer": env("COUNTS_LAYER"),
        "reference_h5ad": env("REFERENCE_H5AD"),
        "reference_name": env("REFERENCE_NAME"),
        "reference_label_key": env("REFERENCE_LABEL_KEY"),
        "reference_batch_key": env("REFERENCE_BATCH_KEY"),
        "reference_sample_key": env("REFERENCE_SAMPLE_KEY"),
        "reference_tissue_key": env("REFERENCE_TISSUE_KEY"),
        "reference_tissue_filter": env("REFERENCE_TISSUE_FILTER"),
        "reference_species": env("REFERENCE_SPECIES"),
        "query_label_value": env("QUERY_LABEL_VALUE"),
        "prediction_min_probability": env("PREDICTION_MIN_PROBABILITY"),
        "max_epochs_scvi": env("MAX_EPOCHS_SCVI"),
        "max_epochs_scanvi": env("MAX_EPOCHS_SCANVI"),
        "top_n_candidates": env("TOP_N_CANDIDATES"),
        "seed": env("SEED"),
        "use_gpu": env("USE_GPU"),
        "write_h5ad": env("WRITE_H5AD"),
        "write_latent": env("WRITE_LATENT"),
        "write_model": env("WRITE_MODEL"),
    }
    for key, value in overrides.items():
        if value not in {"", None}:
            params[key] = value
    return params


def filter_reference(reference: Any, params: dict[str, Any], warnings: list[str]) -> Any:
    tissue_key = str(params.get("reference_tissue_key") or "").strip()
    tissue_filter = str(params.get("reference_tissue_filter") or "").strip()
    if not tissue_key and not tissue_filter:
        return reference
    if tissue_key not in reference.obs:
        warnings.append(f"reference_tissue_key '{tissue_key}' was not found; reference was not tissue-filtered.")
        return reference
    allowed = {value.strip().lower() for value in tissue_filter.split("|") if value.strip()}
    if not allowed:
        return reference
    mask = reference.obs[tissue_key].astype(str).str.lower().isin(allowed)
    filtered = reference[mask].copy()
    if filtered.n_obs == 0:
        raise SystemExit(f"reference_tissue_filter '{tissue_filter}' removed all reference cells.")
    warnings.append(f"Reference was filtered from {reference.n_obs} to {filtered.n_obs} cells by {tissue_key}={tissue_filter}.")
    return filtered


def validate_reference(reference: Any, params: dict[str, Any]) -> None:
    label_key = params["reference_label_key"]
    if label_key not in reference.obs:
        raise SystemExit(f"reference_label_key '{label_key}' was not found in reference.obs")
    labels = reference.obs[label_key].astype(str)
    labels = labels[labels.ne("") & labels.ne("nan")]
    if labels.empty:
        raise SystemExit(f"reference_label_key '{label_key}' contains no usable labels")


def prepare_count_layer(adata: Any, counts_layer: str, warnings: list[str], role: str) -> None:
    layer = str(counts_layer or "X")
    if layer.lower() == "x":
        adata.layers["_izkf_counts"] = adata.X.copy()
    elif layer in adata.layers:
        adata.layers["_izkf_counts"] = adata.layers[layer].copy()
    else:
        warnings.append(f"{role} counts_layer '{layer}' was not found; using X. Confirm this is raw count-like data.")
        adata.layers["_izkf_counts"] = adata.X.copy()


def warn_if_count_layer_suspicious(adata: Any, layer: str, warnings: list[str], role: str) -> None:
    import numpy as np
    from scipy import sparse

    x = adata.layers[layer]
    sample = x[: min(200, adata.n_obs), : min(200, adata.n_vars)]
    values = sample.data if sparse.issparse(sample) else np.asarray(sample).ravel()
    if values.size == 0:
        return
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return
    frac_integer = float(np.mean(np.isclose(finite, np.round(finite))))
    if float(np.nanmax(finite)) < 20 and frac_integer < 0.95:
        warnings.append(f"{role} count layer looks non-integer/log-normalized; scVI/scANVI expects raw count-like values.")


def harmonize_genes(query: Any, reference: Any) -> list[str]:
    reference_genes = {str(gene) for gene in reference.var_names}
    return [str(gene) for gene in query.var_names.astype(str) if str(gene) in reference_genes]


def build_combined_adata(query: Any, reference: Any, params: dict[str, Any]) -> Any:
    import anndata as ad
    import pandas as pd

    query = query.copy()
    reference = reference.copy()
    query.obs["_izkf_original_cell_id"] = query.obs_names.astype(str)
    reference.obs["_izkf_original_cell_id"] = reference.obs_names.astype(str)
    query.obs_names = "query::" + query.obs_names.astype(str)
    reference.obs_names = "reference::" + reference.obs_names.astype(str)

    source_key = params["source_key"]
    labels_key = params["labels_key"]
    batch_key = params["batch_key"]
    query.obs[source_key] = "query"
    reference.obs[source_key] = "reference"
    query.obs[labels_key] = params["query_label_value"]
    reference.obs[labels_key] = reference.obs[params["reference_label_key"]].astype(str).replace({"": params["query_label_value"], "nan": params["query_label_value"]})
    query.obs[batch_key] = build_batch_series(query.obs, params.get("sample_key"), "query")
    reference_batch_source = params.get("reference_batch_key") or params.get("reference_sample_key")
    reference.obs[batch_key] = build_batch_series(reference.obs, reference_batch_source, "reference")

    combined = ad.concat({"reference": reference, "query": query}, axis=0, join="inner", merge="same", index_unique=None)
    for column in [source_key, labels_key, batch_key]:
        combined.obs[column] = pd.Categorical(combined.obs[column].astype(str))
    return combined


def build_batch_series(obs: Any, key: str | None, prefix: str) -> list[str]:
    if key and key in obs:
        return [f"{prefix}:{value}" for value in obs[key].astype(str)]
    return [prefix] * len(obs)


def cell_prediction_rows(adata: Any, predictions: Any, probabilities: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    cluster_key = params.get("cluster_key") or ""
    sample_key = params.get("sample_key") or ""
    threshold = float(params["prediction_min_probability"])
    top_n = int(params["top_n_candidates"])
    for cell_name in adata.obs_names.astype(str):
        probs = probabilities.loc[cell_name].astype(float).sort_values(ascending=False)
        candidates = list(probs.head(top_n).items())
        max_probability = float(candidates[0][1]) if candidates else 0.0
        entropy = probability_entropy(probs.values)
        top_label = str(predictions.loc[cell_name])
        row: dict[str, Any] = {
            "cell_id": str(adata.obs.loc[cell_name, "_izkf_original_cell_id"]),
            "cluster_id": str(adata.obs.loc[cell_name, cluster_key]) if cluster_key in adata.obs else "",
            "sample_id": str(adata.obs.loc[cell_name, sample_key]) if sample_key in adata.obs else "",
            "top_label": top_label,
            "confidence_bucket": confidence_bucket(max_probability, threshold),
            "max_probability": round(max_probability, 6),
            "entropy": round(entropy, 6),
            "review_status": review_status(max_probability, threshold),
        }
        for index in range(1, 4):
            label, prob = candidates[index - 1] if index <= len(candidates) else ("", "")
            row[f"candidate_{index}"] = str(label)
            row[f"candidate_{index}_probability"] = round(float(prob), 6) if prob != "" else ""
        rows.append(row)
    return rows


def label_summary_rows(cell_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    total = len(cell_rows)
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell_rows:
        by_label[str(row["top_label"])].append(row)
    for label, label_rows_for_label in sorted(by_label.items(), key=lambda item: (-len(item[1]), item[0])):
        probs = [float(row["max_probability"]) for row in label_rows_for_label]
        rows.append(
            {
                "label": label,
                "n_cells": len(label_rows_for_label),
                "fraction_cells": round(len(label_rows_for_label) / total, 6) if total else 0,
                "mean_probability": round(sum(probs) / len(probs), 6) if probs else "",
                "median_probability": round(median(probs), 6) if probs else "",
            }
        )
    return rows


def cluster_summary_rows(cell_rows: list[dict[str, Any]], cluster_key: str) -> list[dict[str, Any]]:
    if not cluster_key:
        return []
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell_rows:
        cluster_id = str(row.get("cluster_id") or "")
        if cluster_id:
            by_cluster[cluster_id].append(row)
    rows = []
    for cluster_id in sorted(by_cluster, key=cluster_sort_key):
        rows_for_cluster = by_cluster[cluster_id]
        labels = Counter(str(row["top_label"]) for row in rows_for_cluster)
        top_label, top_count = labels.most_common(1)[0]
        probs = [float(row["max_probability"]) for row in rows_for_cluster]
        top_fraction = top_count / len(rows_for_cluster)
        median_probability = median(probs)
        status = cluster_review_status(top_fraction, median_probability)
        rows.append(
            {
                "cluster_id": cluster_id,
                "n_cells": len(rows_for_cluster),
                "top_label": top_label,
                "top_label_fraction": round(top_fraction, 6),
                "mean_probability": round(sum(probs) / len(probs), 6) if probs else "",
                "median_probability": round(median_probability, 6) if probs else "",
                "n_predicted_labels": len(labels),
                "label_counts": "; ".join(f"{label}:{count}" for label, count in labels.most_common()),
                "confidence_bucket": confidence_bucket(median_probability, 0.6),
                "review_status": status,
            }
        )
    return rows


def cluster_predictions_from_summary(cluster_rows: list[dict[str, Any]], cell_rows: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell_rows:
        if row.get("cluster_id"):
            by_cluster[str(row["cluster_id"])].append(row)
    predictions = []
    summary_by_cluster = {str(row["cluster_id"]): row for row in cluster_rows}
    for cluster_id in sorted(by_cluster, key=cluster_sort_key):
        rows = by_cluster[cluster_id]
        counts = Counter(str(row["top_label"]) for row in rows)
        candidates = []
        for rank, (label, count) in enumerate(counts.most_common(top_n), start=1):
            label_probs = [float(row["max_probability"]) for row in rows if str(row["top_label"]) == label]
            candidates.append(
                {
                    "rank": rank,
                    "label_raw": label,
                    "label_normalized": normalize_label(label),
                    "ontology_id": None,
                    "provider_score": round(count / len(rows), 6),
                    "provider_score_name": "scanvi_cluster_label_fraction",
                    "confidence_bucket": confidence_bucket(median(label_probs), 0.6),
                    "evidence_items": [
                        {
                            "evidence_type": "scanvi_reference_transfer",
                            "reference_name": "",
                            "n_cells": count,
                            "fraction_cells": round(count / len(rows), 6),
                            "median_probability": round(median(label_probs), 6),
                        }
                    ],
                }
            )
        summary = summary_by_cluster.get(cluster_id, {})
        predictions.append(
            {
                "cluster_id": cluster_id,
                "n_cells": len(rows),
                "top_label": summary.get("top_label"),
                "top_label_normalized": normalize_label(summary.get("top_label", "")),
                "confidence_bucket": summary.get("confidence_bucket", "unknown"),
                "review_status": summary.get("review_status", ""),
                "candidates": candidates,
            }
        )
    return predictions


def cell_predictions_from_rows(cell_rows: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    payload = []
    for row in cell_rows:
        candidates = []
        for rank in range(1, top_n + 1):
            label = row.get(f"candidate_{rank}")
            prob = row.get(f"candidate_{rank}_probability")
            if label in {"", None} or prob in {"", None}:
                continue
            candidates.append(
                {
                    "rank": rank,
                    "label_raw": label,
                    "label_normalized": normalize_label(label),
                    "provider_score": float(prob),
                    "provider_score_name": "scanvi_label_probability",
                    "confidence_bucket": confidence_bucket(float(prob), 0.6) if rank == 1 else None,
                    "evidence": {"probability": float(prob)},
                }
            )
        payload.append(
            {
                "cell_id": row["cell_id"],
                "cluster_id": row.get("cluster_id") or None,
                "top_label": row["top_label"],
                "confidence_bucket": row["confidence_bucket"],
                "candidates": candidates,
            }
        )
    return payload


def reference_summary_rows(**kwargs: Any) -> list[dict[str, Any]]:
    params = kwargs["params"]
    query = kwargs["query"]
    reference = kwargs["reference"]
    combined = kwargs["combined"]
    return [
        {"field": "query_h5ad", "value": str(kwargs["input_h5ad"])},
        {"field": "reference_h5ad", "value": str(kwargs["reference_h5ad"])},
        {"field": "reference_name", "value": params["reference_name"]},
        {"field": "reference_label_key", "value": params["reference_label_key"]},
        {"field": "reference_cells_after_filter", "value": reference.n_obs},
        {"field": "query_cells", "value": query.n_obs},
        {"field": "shared_genes", "value": query.n_vars},
        {"field": "reference_labels", "value": reference.obs[params["reference_label_key"]].astype(str).nunique()},
        {"field": "combined_batches", "value": combined.obs[params["batch_key"]].astype(str).nunique()},
        {"field": "scvi_tools_version", "value": kwargs.get("scvi_version", "")},
    ]


def training_metric_rows(model: Any, model_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    history = getattr(model, "history", None)
    if history is None:
        return rows
    try:
        for metric in history:
            series = history[metric]
            if hasattr(series, "items"):
                for epoch, value in series.items():
                    rows.append({"metric": f"{model_name}_{metric}", "epoch": epoch, "value": float(value)})
    except Exception:
        return []
    return rows


def write_annotated_h5ad(*, input_h5ad: Path, output_h5ad: Path, cell_rows: list[dict[str, Any]], latent: Any, umap: Any, params: dict[str, Any]) -> None:
    import anndata as ad
    import pandas as pd

    adata = ad.read_h5ad(input_h5ad)
    by_cell = {str(row["cell_id"]): row for row in cell_rows}
    aligned = [by_cell.get(str(cell), {}) for cell in adata.obs_names.astype(str)]
    adata.obs[f"{PREFIX}_label"] = [row.get("top_label", "unassigned") for row in aligned]
    adata.obs[f"{PREFIX}_confidence"] = [row.get("confidence_bucket", "unknown") for row in aligned]
    adata.obs[f"{PREFIX}_probability"] = [row.get("max_probability", math.nan) for row in aligned]
    adata.obs[f"{PREFIX}_entropy"] = [row.get("entropy", math.nan) for row in aligned]
    adata.obs[f"{PREFIX}_review_status"] = [row.get("review_status", "missing prediction") for row in aligned]
    for rank in range(1, 4):
        adata.obs[f"{PREFIX}_candidate_{rank}"] = [row.get(f"candidate_{rank}", "") for row in aligned]
        adata.obs[f"{PREFIX}_candidate_{rank}_probability"] = [row.get(f"candidate_{rank}_probability", math.nan) for row in aligned]
    adata.obs[f"{PREFIX}_reference_name"] = params["reference_name"]
    if latent is not None:
        adata.obsm["X_scANVI"] = latent
    if umap is not None:
        adata.obsm["X_scANVI_umap"] = umap
    adata.uns[PREFIX] = {
        "schema_version": SCHEMA_VERSION,
        "template": TEMPLATE_NAME,
        "reference_name": params["reference_name"],
        "reference_label_key": params["reference_label_key"],
        "cell_predictions_json": json.dumps(cell_rows),
    }
    output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(output_h5ad)


def resolve_input_h5ad(params: dict[str, Any]) -> Path:
    raw = str(params.get("input_h5ad") or "").strip()
    if raw:
        return resolve_path(raw, base=TEMPLATE_DIR)
    upstream = PROJECT_DIR / "scrna_prep" / "results" / "adata.prep.h5ad"
    if upstream.exists():
        params["input_source_template"] = params.get("input_source_template") or "scrna_prep"
        return upstream.resolve()
    fallback = TEMPLATE_DIR.parent / "scrna_prep" / "results" / "adata.prep.h5ad"
    return fallback.resolve()


def resolve_reference_h5ad(params: dict[str, Any]) -> Path:
    raw = str(params.get("reference_h5ad") or "").strip()
    if not raw:
        raise SystemExit("reference_h5ad is required. Set REFERENCE_H5AD or [reference] reference_h5ad.")
    return resolve_path(raw, base=TEMPLATE_DIR)


def resolve_path(value: str, *, base: Path) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def render_report() -> None:
    source = TEMPLATE_DIR / "report.qmd"
    target = RESULTS_DIR / "report.qmd"
    shutil.copyfile(source, target)
    if shutil.which("quarto"):
        subprocess.run(["quarto", "render", str(target), "--to", "html"], cwd=RESULTS_DIR, check=True)
    else:
        progress("quarto not found; report.qmd was written but HTML was not rendered")


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value not in {"", None} else None


def bool_param(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def accelerator_arg(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"true", "gpu", "cuda"}:
        return "gpu"
    if text in {"false", "cpu"}:
        return "cpu"
    return "auto"


def set_scvi_seed(seed: int, *, scvi: Any) -> None:
    try:
        scvi.settings.seed = seed
    except Exception:
        pass


def confidence_bucket(probability: float, threshold: float) -> str:
    if probability >= max(0.85, threshold):
        return "high"
    if probability >= threshold:
        return "medium"
    if probability >= 0.35:
        return "low"
    return "very low"


def review_status(probability: float, threshold: float) -> str:
    return "review candidate" if probability >= threshold else "low confidence review"


def cluster_review_status(top_fraction: float, median_probability: float) -> str:
    if top_fraction >= 0.75 and median_probability >= 0.7:
        return "accepted candidate"
    if median_probability < 0.6:
        return "low confidence"
    if top_fraction < 0.6:
        return "mixed cluster"
    return "review candidate"


def probability_entropy(values: Any) -> float:
    vals = [float(v) for v in values if float(v) > 0]
    if not vals:
        return 0.0
    entropy = -sum(v * math.log(v) for v in vals)
    return entropy / math.log(len(vals)) if len(vals) > 1 else 0.0


def median(values: list[float]) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[midpoint])
    return float((ordered[midpoint - 1] + ordered[midpoint]) / 2)


def cluster_sort_key(value: Any) -> tuple[int, Any]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def normalize_label(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def progress(message: str) -> None:
    print(f"[{TEMPLATE_NAME}] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
