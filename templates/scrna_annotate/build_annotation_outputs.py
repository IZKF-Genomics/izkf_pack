#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tomllib

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parent
LIB_DIR = ROOT / "lib"
import sys
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from annotation_io import (
    load_adata,
    load_marker_sets,
    require_obs_column,
    resolve_optional_obs_column,
    resolve_sample_display,
)
from annotation_methods import (
    apply_cluster_suggestions,
    run_celltypist_annotation,
    summarize_cluster_predictions,
)
from annotation_review import merge_marker_review, score_marker_sets


def load_config(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_table(path: Path, df: pd.DataFrame) -> None:
    ensure_parent(path)
    df.to_csv(path, index=False)


def write_yaml(path: Path, payload: dict) -> None:
    ensure_parent(path)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def main() -> int:
    cfg = load_config(ROOT / "config" / "project.toml")
    adata, input_path = load_adata(str(cfg["input"]["input_h5ad"]))

    cluster_key = str(cfg["metadata"]["cluster_key"]).strip() or "leiden"
    batch_key = str(cfg["metadata"]["batch_key"]).strip() or "batch"
    condition_key = str(cfg["metadata"]["condition_key"]).strip() or "condition"
    sample_id_key = str(cfg["metadata"]["sample_id_key"]).strip() or "sample_id"
    sample_label_key = str(cfg["metadata"]["sample_label_key"]).strip() or "sample_display"
    predicted_label_key = str(cfg["annotation"]["predicted_label_key"]).strip() or "predicted_label"
    final_label_key = str(cfg["annotation"]["final_label_key"]).strip() or "final_label"
    unknown_label = str(cfg["annotation"]["unknown_label"]).strip() or "Unknown"
    annotation_method = str(cfg["annotation"]["annotation_method"]).strip().lower()
    raw_methods = str(cfg["annotation"].get("annotation_methods", "")).strip()
    selected_methods = [item.strip().lower() for item in raw_methods.split(",") if item.strip()] if raw_methods else [annotation_method]
    if not selected_methods:
        selected_methods = [annotation_method]

    require_obs_column(adata, cluster_key, allow_single_category=True)
    adata.obs[batch_key] = resolve_optional_obs_column(adata, batch_key, fallback="unknown")
    adata.obs[condition_key] = resolve_optional_obs_column(adata, condition_key, fallback="unknown")
    adata.obs[sample_id_key] = resolve_optional_obs_column(adata, sample_id_key, fallback="unknown")
    adata.obs["sample_display"] = resolve_sample_display(adata, sample_id_key, sample_label_key)
    if "X_umap" not in adata.obsm:
        raise RuntimeError("The input object does not contain X_umap. Run scrna_prep or provide an object with a UMAP embedding before annotation review.")

    out_adata = ROOT / str(cfg["output"]["adata_file"])
    cell_prediction_file = ROOT / str(cfg["output"]["cell_annotation_predictions_file"])
    cluster_summary_file = ROOT / str(cfg["output"]["cluster_annotation_summary_file"])
    marker_summary_file = ROOT / str(cfg["output"]["marker_review_summary_file"])
    annotation_status_file = ROOT / str(cfg["output"]["annotation_status_summary_file"])
    method_comparison_file = ROOT / str(cfg["output"]["method_comparison_file"])
    report_context_file = ROOT / str(cfg["output"]["report_context_file"])

    method_comparison_rows: list[dict[str, object]] = []
    top_label_summary = pd.DataFrame()
    probability_matrix = pd.DataFrame()

    if "celltypist" in selected_methods:
        prediction_df, probability_matrix = run_celltypist_annotation(
            adata,
            model=str(cfg["annotation"]["celltypist_model"]).strip(),
            mode=str(cfg["annotation"]["celltypist_mode"]).strip() or "best_match",
            p_thres=float(cfg["annotation"]["celltypist_p_thres"]),
            use_gpu=bool(cfg["annotation"]["use_gpu"]),
            predicted_label_key=predicted_label_key,
        )
        adata.obs[predicted_label_key] = prediction_df[predicted_label_key]
        adata.obs["predicted_confidence"] = prediction_df["predicted_confidence"]
        cluster_summary, top_label_summary = summarize_cluster_predictions(
            adata.obs[[cluster_key, predicted_label_key, "predicted_confidence"]].copy(),
            cluster_key=cluster_key,
            predicted_label_key=predicted_label_key,
            confidence_key="predicted_confidence",
            min_fraction=float(cfg["annotation"]["majority_vote_min_fraction"]),
            confidence_threshold=float(cfg["annotation"]["confidence_threshold"]),
            unknown_label=unknown_label,
            top_n=int(cfg["annotation"]["rank_top_markers"]),
        )

        marker_sets = load_marker_sets(str(cfg["annotation"]["marker_file"]))
        marker_summary, marker_long_scores = score_marker_sets(adata, marker_sets, cluster_key=cluster_key)
        cluster_summary = merge_marker_review(cluster_summary, marker_summary)

        annotated_obs = apply_cluster_suggestions(
            adata.obs[[cluster_key, predicted_label_key, "predicted_confidence", batch_key, condition_key, sample_id_key, "sample_display"]].copy(),
            cluster_summary,
            cluster_key=cluster_key,
            final_label_key=final_label_key,
            unknown_label=unknown_label,
        )
        for col in annotated_obs.columns:
            adata.obs[col] = annotated_obs[col].to_numpy()

        status_summary = (
            cluster_summary["annotation_status"]
            .value_counts(dropna=False)
            .rename_axis("annotation_status")
            .reset_index(name="n_clusters")
        )
        cell_predictions = adata.obs[
            [
                sample_id_key,
                cluster_key,
                predicted_label_key,
                "predicted_confidence",
                "cluster_suggested_label",
                "annotation_status",
                final_label_key,
            ]
        ].reset_index(names="cell_id")
        write_table(cell_prediction_file, cell_predictions)
        write_table(cluster_summary_file, cluster_summary)
        write_table(marker_summary_file, marker_long_scores if not marker_long_scores.empty else marker_summary)
        write_table(annotation_status_file, status_summary)

        method_comparison_rows.append(
            {
                "method": "celltypist",
                "model": str(cfg["annotation"]["celltypist_model"]).strip(),
                "n_predicted_labels": int(adata.obs[predicted_label_key].nunique()),
                "mean_confidence": float(adata.obs["predicted_confidence"].mean()),
                "n_review_needed_clusters": int(cluster_summary["annotation_status"].astype(str).str.startswith("review_needed").sum()),
                "n_accepted_clusters": int((cluster_summary["annotation_status"] == "accepted").sum()),
            }
        )

        celltypist_dir = ROOT / "results" / "methods" / "celltypist"
        write_table(celltypist_dir / "probability_matrix.csv", probability_matrix.reset_index(names="cell_id"))
        write_table(celltypist_dir / "top_label_summary.csv", top_label_summary)
    else:
        raise RuntimeError("No supported annotation methods were selected.")

    method_comparison = pd.DataFrame(method_comparison_rows)
    write_table(method_comparison_file, method_comparison)

    adata.uns["annotation_method"] = annotation_method
    adata.uns["annotation_methods"] = selected_methods
    adata.uns["annotation_model"] = str(cfg["annotation"]["celltypist_model"]).strip()
    adata.uns["input_h5ad"] = str(input_path)
    adata.uns["input_source_template"] = str(cfg["input"]["input_source_template"])
    adata.uns["cluster_key"] = cluster_key
    adata.uns["predicted_label_key"] = predicted_label_key
    adata.uns["final_label_key"] = final_label_key
    adata.uns["annotation_unknown_label"] = unknown_label
    ensure_parent(out_adata)
    adata.write_h5ad(out_adata)

    context = {
        "input_h5ad": str(input_path),
        "input_source_template": str(cfg["input"]["input_source_template"]),
        "cluster_key": cluster_key,
        "batch_key": batch_key,
        "condition_key": condition_key,
        "sample_id_key": sample_id_key,
        "sample_label_key": sample_label_key,
        "predicted_label_key": predicted_label_key,
        "final_label_key": final_label_key,
        "unknown_label": unknown_label,
        "selected_methods": selected_methods,
        "tables": {
            "cell_annotation_predictions": "results/tables/cell_annotation_predictions.csv",
            "cluster_annotation_summary": "results/tables/cluster_annotation_summary.csv",
            "marker_review_summary": "results/tables/marker_review_summary.csv",
            "annotation_status_summary": "results/tables/annotation_status_summary.csv",
            "method_comparison": "results/tables/method_comparison.csv",
            "celltypist_probability_matrix": "results/methods/celltypist/probability_matrix.csv",
            "celltypist_top_label_summary": "results/methods/celltypist/top_label_summary.csv",
        },
        "adata_file": "results/adata.annotated.h5ad",
        "report_files": [
            "00_annotation_overview.html",
            "01_celltypist.html",
            "02_scanvi.html",
            "03_decoupler_review.html",
            "04_scdeepsort.html",
            "05_scgpt.html",
        ],
    }
    write_yaml(report_context_file, context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
