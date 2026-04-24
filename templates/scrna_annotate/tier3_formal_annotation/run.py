#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import html
import sys

import anndata as ad
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "shared" / "lib"
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
from workflow_io import ensure_directory, load_workflow_config, read_yaml, resolve_global_value


TIER_DIR = Path(__file__).resolve().parent
RESULTS_DIR = TIER_DIR / "results"
REPORTS_DIR = TIER_DIR / "reports"
TABLES_DIR = RESULTS_DIR / "tables"
METHODS_DIR = RESULTS_DIR / "methods" / "celltypist"
CONFIG_PATH = TIER_DIR / "config" / "00_formal_annotation_config.yaml"
TIER2_ADATA = ROOT / "tier2_refinement" / "results" / "adata.refined.h5ad"
TIER2_CONFIG = ROOT / "tier2_refinement" / "config" / "00_refinement_config.yaml"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_table(path: Path, df: pd.DataFrame) -> None:
    ensure_parent(path)
    df.to_csv(path, index=False)


def _bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _table_html(df: pd.DataFrame, *, limit: int = 10) -> str:
    if df.empty:
        return "<p>No rows to display.</p>"
    return df.head(limit).to_html(index=False, border=0, classes="dataframe")


def main() -> int:
    workflow_cfg, workflow_path = load_workflow_config()
    tier_cfg = read_yaml(CONFIG_PATH)
    tier2_cfg = read_yaml(TIER2_CONFIG)

    if not TIER2_ADATA.exists():
        raise SystemExit("Tier 3 requires Tier 2 outputs. Run ./run.sh --tier tier2 first or ./run.sh --from tier1 --to tier3.")

    ensure_directory(TABLES_DIR)
    ensure_directory(REPORTS_DIR)
    ensure_directory(METHODS_DIR)

    formal_cfg = tier_cfg.get("formal_annotation", {}) if isinstance(tier_cfg.get("formal_annotation"), dict) else {}
    celltypist_cfg = tier_cfg.get("celltypist", {}) if isinstance(tier_cfg.get("celltypist"), dict) else {}

    enabled = _bool(formal_cfg.get("enabled", False))
    method = str(formal_cfg.get("method", "celltypist")).strip() or "celltypist"
    model = str(celltypist_cfg.get("model", "")).strip()
    mode = str(celltypist_cfg.get("mode", "best_match")).strip() or "best_match"
    p_thres = float(celltypist_cfg.get("p_thres", 0.5))
    use_gpu = _bool(celltypist_cfg.get("use_gpu", False))

    cluster_key = resolve_global_value(workflow_cfg, "cluster_key", "leiden")
    batch_key = resolve_global_value(workflow_cfg, "batch_key", "batch")
    condition_key = resolve_global_value(workflow_cfg, "condition_key", "condition")
    sample_id_key = resolve_global_value(workflow_cfg, "sample_id_key", "sample_id")
    sample_label_key = resolve_global_value(workflow_cfg, "sample_label_key", "sample_display")
    unknown_label = resolve_global_value(workflow_cfg, "unknown_label", "Unknown")
    predicted_label_key = str(formal_cfg.get("predicted_label_key", "formal_label_celltypist")).strip() or "formal_label_celltypist"
    final_label_key = str(formal_cfg.get("final_label_key", "final_label")).strip() or "final_label"
    majority_vote_min_fraction = float(formal_cfg.get("majority_vote_min_fraction", 0.6))
    confidence_threshold = float(formal_cfg.get("confidence_threshold", 0.5))
    rank_top_markers = int(formal_cfg.get("rank_top_markers", 5))
    marker_file = str(formal_cfg.get("marker_file", "")).strip()
    if not marker_file:
        marker_file = str(tier2_cfg.get("refinement", {}).get("marker_file", "")).strip()

    adata, input_path = load_adata(str(TIER2_ADATA))
    require_obs_column(adata, cluster_key, allow_single_category=True)
    adata.obs[batch_key] = resolve_optional_obs_column(adata, batch_key, fallback="unknown")
    adata.obs[condition_key] = resolve_optional_obs_column(adata, condition_key, fallback="unknown")
    adata.obs[sample_id_key] = resolve_optional_obs_column(adata, sample_id_key, fallback="unknown")
    adata.obs["sample_display"] = resolve_sample_display(adata, sample_id_key, sample_label_key)
    if "X_umap" not in adata.obsm:
        raise SystemExit("Tier 3 expects X_umap in the Tier 2 output object.")

    cell_predictions = pd.DataFrame()
    cluster_summary = pd.DataFrame()
    marker_summary = pd.DataFrame()
    marker_long = pd.DataFrame()
    status_summary = pd.DataFrame()
    method_comparison = pd.DataFrame()
    probability_matrix = pd.DataFrame(columns=["cell_id"])
    top_label_summary = pd.DataFrame(columns=["cluster", "predicted_label", "n_cells", "fraction"])
    execution_status = "not_run"
    message = ""

    if not enabled:
        message = "Tier 3 formal annotation is configured but disabled. Set formal_annotation.enabled to true to execute CellTypist."
    elif method != "celltypist":
        message = f"Formal annotation method '{method}' is not implemented yet in the rebuilt workflow."
    elif not model:
        message = "CellTypist was enabled but no model was configured. Set tier3_formal_annotation/config/00_formal_annotation_config.yaml."
    else:
        prediction_df, probability_matrix_raw = run_celltypist_annotation(
            adata,
            model=model,
            mode=mode,
            p_thres=p_thres,
            use_gpu=use_gpu,
            predicted_label_key=predicted_label_key,
        )
        adata.obs[predicted_label_key] = prediction_df[predicted_label_key]
        adata.obs["formal_confidence"] = prediction_df["predicted_confidence"]
        cluster_summary, top_label_summary = summarize_cluster_predictions(
            adata.obs[[cluster_key, predicted_label_key, "formal_confidence"]].copy(),
            cluster_key=cluster_key,
            predicted_label_key=predicted_label_key,
            confidence_key="formal_confidence",
            min_fraction=majority_vote_min_fraction,
            confidence_threshold=confidence_threshold,
            unknown_label=unknown_label,
            top_n=rank_top_markers,
        )
        marker_sets = load_marker_sets(marker_file)
        marker_summary, marker_long = score_marker_sets(adata, marker_sets, cluster_key=cluster_key)
        cluster_summary = merge_marker_review(cluster_summary, marker_summary)

        annotated_obs = apply_cluster_suggestions(
            adata.obs[[cluster_key, predicted_label_key, "formal_confidence", batch_key, condition_key, sample_id_key, "sample_display"]].copy(),
            cluster_summary,
            cluster_key=cluster_key,
            final_label_key=final_label_key,
            unknown_label=unknown_label,
        )
        for col in annotated_obs.columns:
            adata.obs[col] = annotated_obs[col].to_numpy()

        adata.uns["formal_annotation_method"] = method
        adata.uns["formal_annotation_model"] = model
        adata.uns["formal_annotation_enabled"] = True
        adata.uns["cluster_key"] = cluster_key
        adata.uns["final_label_key"] = final_label_key
        adata.uns["predicted_label_key"] = predicted_label_key
        adata.uns["annotation_unknown_label"] = unknown_label
        adata.write_h5ad(RESULTS_DIR / "adata.annotated.h5ad")

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
                "formal_confidence",
                "cluster_suggested_label",
                "annotation_status",
                final_label_key,
            ]
        ].reset_index(names="cell_id")
        cell_predictions = cell_predictions.rename(columns={"formal_confidence": "predicted_confidence"})
        method_comparison = pd.DataFrame(
            [
                {
                    "method": "celltypist",
                    "model": model,
                    "n_predicted_labels": int(adata.obs[predicted_label_key].nunique()),
                    "mean_confidence": float(adata.obs["formal_confidence"].mean()),
                    "n_review_needed_clusters": int(cluster_summary["annotation_status"].astype(str).str.startswith("review_needed").sum()),
                    "n_accepted_clusters": int((cluster_summary["annotation_status"] == "accepted").sum()),
                }
            ]
        )
        probability_matrix = probability_matrix_raw.reset_index(names="cell_id")
        execution_status = "complete"
        message = "CellTypist formal annotation completed successfully."

    if not cell_predictions.empty:
        write_table(TABLES_DIR / "formal_annotation_predictions.csv", cell_predictions)
        write_table(TABLES_DIR / "formal_annotation_summary.csv", cluster_summary)
        write_table(TABLES_DIR / "annotation_status_summary.csv", status_summary)
        write_table(TABLES_DIR / "method_comparison.csv", method_comparison)
        write_table(TABLES_DIR / "marker_review_summary.csv", marker_long if not marker_long.empty else marker_summary)
        write_table(METHODS_DIR / "probability_matrix.csv", probability_matrix)
        write_table(METHODS_DIR / "top_label_summary.csv", top_label_summary)

    run_info = {
        "tier": "tier3_formal_annotation",
        "status": execution_status,
        "workflow_config": str(workflow_path),
        "input_h5ad": str(input_path),
        "formal_annotation_enabled": enabled,
        "formal_method": method,
        "celltypist_model": model,
        "marker_file": marker_file,
        "message": message,
    }
    (RESULTS_DIR / "run_info.yaml").write_text(yaml.safe_dump(run_info, sort_keys=False), encoding="utf-8")

    cluster_table_html = _table_html(cluster_summary)
    status_table_html = _table_html(status_summary)
    prediction_table_html = _table_html(cell_predictions)
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Tier 3 Formal Annotation</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem auto; max-width: 1100px; line-height: 1.5; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    code {{ background: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 4px; }}
    .box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #e5e7eb; }}
  </style>
</head>
<body>
  <h1>Tier 3 Formal Annotation</h1>
  <p>This layer runs formal, reference-aware annotation after Tier 1 preview and Tier 2 refinement.</p>
  <div class="box">
    <h2>Status</h2>
    <p><strong>Execution status:</strong> {html.escape(execution_status)}</p>
    <p><strong>Method:</strong> <code>{html.escape(method)}</code></p>
    <p><strong>Model:</strong> <code>{html.escape(model or "none")}</code></p>
    <p>{html.escape(message)}</p>
  </div>
  <div class="box">
    <h2>Configuration</h2>
    <p><strong>Cluster key:</strong> <code>{html.escape(cluster_key)}</code></p>
    <p><strong>Predicted label key:</strong> <code>{html.escape(predicted_label_key)}</code></p>
    <p><strong>Final label key:</strong> <code>{html.escape(final_label_key)}</code></p>
    <p><strong>Marker file:</strong> <code>{html.escape(marker_file or "none")}</code></p>
  </div>
  <div class="box">
    <h2>Annotation Status Summary</h2>
    {status_table_html}
  </div>
  <div class="box">
    <h2>Cluster Summary</h2>
    {cluster_table_html}
  </div>
  <div class="box">
    <h2>Cell Prediction Preview</h2>
    {prediction_table_html}
  </div>
</body>
</html>
"""
    (REPORTS_DIR / "03_formal_annotation.html").write_text(html_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
