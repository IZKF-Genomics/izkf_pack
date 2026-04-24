#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

import anndata as ad
import pandas as pd
import scanpy as sc
import yaml


ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "shared" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from annotation_io import load_adata, require_obs_column, resolve_optional_obs_column, resolve_sample_display
from workflow_io import ensure_directory, load_workflow_config, read_yaml, resolve_global_value


TIER_DIR = Path(__file__).resolve().parent
RESULTS_DIR = TIER_DIR / "results"
REPORTS_DIR = TIER_DIR / "reports"
TABLES_DIR = RESULTS_DIR / "tables"
CONFIG_PATH = TIER_DIR / "config" / "00_quick_preview_config.yaml"


def build_cluster_summary(adata, *, cluster_key: str, sample_id_key: str, unknown_label: str) -> pd.DataFrame:
    summary = (
        adata.obs[[cluster_key, sample_id_key]]
        .groupby(cluster_key, dropna=False, observed=False)
        .agg(
            n_cells=(sample_id_key, "size"),
            n_samples=(sample_id_key, lambda s: s.astype(str).nunique()),
        )
        .reset_index()
        .rename(columns={cluster_key: "cluster"})
    )
    summary["preview_consensus_label"] = unknown_label
    summary["preview_disagreement_flag"] = False
    summary["preview_review_priority"] = "needs_refinement"
    summary["recommendation"] = "Review cluster markers and lineage context in Tier 2."
    return summary


def build_top_marker_table(adata, *, cluster_key: str, top_n: int = 5) -> pd.DataFrame:
    if adata.n_obs == 0 or adata.n_vars == 0:
        return pd.DataFrame(columns=["cluster", "rank", "gene", "score", "logfoldchange", "pvals_adj"])

    ranked = adata.copy()
    if "counts" in ranked.layers:
        ranked.X = ranked.layers["counts"].copy()
    sc.pp.normalize_total(ranked, target_sum=1e4)
    sc.pp.log1p(ranked)
    try:
        sc.tl.rank_genes_groups(ranked, groupby=cluster_key, method="wilcoxon", use_raw=False)
    except Exception:
        return pd.DataFrame(columns=["cluster", "rank", "gene", "score", "logfoldchange", "pvals_adj"])

    groups = ranked.uns.get("rank_genes_groups", {})
    names = groups.get("names")
    if names is None:
        return pd.DataFrame(columns=["cluster", "rank", "gene", "score", "logfoldchange", "pvals_adj"])

    rows: list[dict[str, object]] = []
    group_names = list(names.dtype.names or [])
    scores = groups.get("scores")
    logfoldchanges = groups.get("logfoldchanges")
    pvals_adj = groups.get("pvals_adj")
    for group in group_names:
        for idx in range(min(top_n, len(names[group]))):
            rows.append(
                {
                    "cluster": str(group),
                    "rank": idx + 1,
                    "gene": str(names[group][idx]),
                    "score": float(scores[group][idx]) if scores is not None else pd.NA,
                    "logfoldchange": float(logfoldchanges[group][idx]) if logfoldchanges is not None else pd.NA,
                    "pvals_adj": float(pvals_adj[group][idx]) if pvals_adj is not None else pd.NA,
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    workflow_cfg, workflow_path = load_workflow_config()
    tier_cfg = read_yaml(CONFIG_PATH)

    input_h5ad = resolve_global_value(workflow_cfg, "input_h5ad")
    cluster_key = resolve_global_value(workflow_cfg, "cluster_key", "leiden")
    sample_id_key = resolve_global_value(workflow_cfg, "sample_id_key", "sample_id")
    batch_key = resolve_global_value(workflow_cfg, "batch_key", "batch")
    condition_key = resolve_global_value(workflow_cfg, "condition_key", "condition")
    unknown_label = (
        str(tier_cfg.get("quick_preview", {}).get("unknown_label", "")).strip()
        or resolve_global_value(workflow_cfg, "unknown_label", "Unknown")
    )

    if not input_h5ad:
        raise SystemExit("Set global.input_h5ad in config/workflow.yaml before running Tier 1.")

    try:
        adata, adata_path = load_adata(input_h5ad)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        require_obs_column(adata, cluster_key, allow_single_category=True)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if "X_umap" not in adata.obsm:
        raise SystemExit("Tier 1 expects X_umap in the input object so the preview report can be interpreted.")

    adata.obs[sample_id_key] = resolve_optional_obs_column(adata, sample_id_key, fallback="unknown")
    adata.obs[batch_key] = resolve_optional_obs_column(adata, batch_key, fallback="unknown")
    adata.obs[condition_key] = resolve_optional_obs_column(adata, condition_key, fallback="unknown")
    adata.obs["sample_display"] = resolve_sample_display(adata, sample_id_key, resolve_global_value(workflow_cfg, "sample_label_key", "sample_display"))

    ensure_directory(TABLES_DIR)
    ensure_directory(REPORTS_DIR)

    preview_methods = tier_cfg.get("quick_preview", {}).get("methods", [])
    methods = [str(item).strip() for item in preview_methods if str(item).strip()]
    if "manual_review" not in methods:
        methods.insert(0, "manual_review")

    preview_obs = adata.obs.copy()
    preview_obs["preview_consensus_label"] = unknown_label
    preview_obs["preview_disagreement_flag"] = False
    preview_obs["preview_review_priority"] = "needs_refinement"
    preview_obs["preview_method_status"] = "manual_review_baseline"

    preview_table = (
        preview_obs[[cluster_key]]
        .reset_index(names="cell_id")
        .assign(preview_consensus_label=unknown_label, preview_disagreement_flag=False, preview_review_priority="needs_refinement")
    )
    preview_table.to_csv(TABLES_DIR / "preview_consensus.csv", index=False)

    disagreement_summary = build_cluster_summary(
        adata,
        cluster_key=cluster_key,
        sample_id_key=sample_id_key,
        unknown_label=unknown_label,
    )
    disagreement_summary.to_csv(TABLES_DIR / "preview_disagreement_summary.csv", index=False)
    top_markers = build_top_marker_table(adata, cluster_key=cluster_key, top_n=5)
    top_markers.to_csv(TABLES_DIR / "cluster_top_markers.csv", index=False)

    adata.obs["preview_consensus_label"] = preview_obs["preview_consensus_label"].to_numpy()
    adata.obs["preview_disagreement_flag"] = preview_obs["preview_disagreement_flag"].to_numpy()
    adata.obs["preview_review_priority"] = preview_obs["preview_review_priority"].to_numpy()
    adata.obs["preview_method_status"] = preview_obs["preview_method_status"].to_numpy()
    adata.uns["scrna_annotate_workflow_config"] = str(workflow_path)
    adata.uns["scrna_annotate_tier1_methods"] = methods
    adata.uns["scrna_annotate_tier1_status"] = "scaffold_preview_complete"
    adata.write_h5ad(RESULTS_DIR / "adata.preview.h5ad")

    report_payload = {
        "tier": "tier1_quick_preview",
        "status": "complete",
        "workflow_config": str(workflow_path),
        "input_h5ad": str(adata_path),
        "cluster_key": cluster_key,
        "methods_requested": methods,
        "methods_executed": ["manual_review"],
        "summary": {
            "n_cells": int(adata.n_obs),
            "n_genes": int(adata.n_vars),
            "n_clusters": int(adata.obs[cluster_key].astype(str).nunique()),
            "top_marker_rows": int(len(top_markers)),
        },
        "next_step": "Run Tier 2 refinement to add marker-backed evidence before formal annotation.",
    }
    (RESULTS_DIR / "run_info.yaml").write_text(yaml.safe_dump(report_payload, sort_keys=False), encoding="utf-8")

    marker_preview_html = ""
    if top_markers.empty:
        marker_preview_html = "<p>No cluster top-marker table was produced. This can happen when ranking fails on the current input representation.</p>"
    else:
        marker_lines = []
        for cluster, group in top_markers.groupby("cluster", observed=False):
            genes = ", ".join(group.sort_values("rank")["gene"].head(5).astype(str))
            marker_lines.append(f"<li><strong>Cluster {cluster}</strong>: {genes}</li>")
        marker_preview_html = "<ul>" + "".join(marker_lines[:12]) + "</ul>"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Tier 1 Quick Preview</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem auto; max-width: 900px; line-height: 1.5; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    code {{ background: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 4px; }}
    .box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }}
  </style>
</head>
<body>
  <h1>Tier 1 Quick Preview</h1>
  <p>This is the new low-setup entry point for <code>scrna_annotate</code>.</p>
  <div class="box">
    <h2>Current Status</h2>
    <p>The Tier 1 scaffold completed successfully.</p>
    <p>Requested preview methods: {", ".join(methods) if methods else "none"}</p>
    <p>Executed methods in this scaffold build: manual_review baseline only.</p>
  </div>
  <div class="box">
    <h2>Dataset Summary</h2>
    <p>Input: <code>{adata_path}</code></p>
    <p>Cells: {adata.n_obs:,}</p>
    <p>Genes: {adata.n_vars:,}</p>
    <p>Clusters in <code>{cluster_key}</code>: {adata.obs[cluster_key].astype(str).nunique():,}</p>
  </div>
  <div class="box">
    <h2>What This Means</h2>
    <p>This scaffold writes conservative preview labels as <code>{unknown_label}</code> so the rebuilt workflow can be exercised safely before quick-preview tools are fully integrated.</p>
    <p>The preview tables tell the user that every cluster should proceed to Tier 2 refinement rather than being accepted automatically.</p>
  </div>
  <div class="box">
    <h2>Cluster Overview</h2>
    <p>Tier 1 now also writes a cluster-level summary and a top-marker table so the next tier has concrete review inputs.</p>
    <p>Cluster summary file: <code>results/tables/preview_disagreement_summary.csv</code></p>
    <p>Top marker file: <code>results/tables/cluster_top_markers.csv</code></p>
  </div>
  <div class="box">
    <h2>Top Markers Preview</h2>
    {marker_preview_html}
  </div>
  <div class="box">
    <h2>Recommended Next Step</h2>
    <p>Run Tier 2 refinement to add marker-backed evidence and cluster-level review before any formal annotation method is enabled.</p>
  </div>
</body>
</html>
"""
    (REPORTS_DIR / "01_quick_preview.html").write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
