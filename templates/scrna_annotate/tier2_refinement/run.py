#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

import anndata as ad
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "shared" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from annotation_io import load_marker_sets
from annotation_review import score_marker_sets
from workflow_io import ensure_directory, load_workflow_config, read_yaml, resolve_global_value


TIER_DIR = Path(__file__).resolve().parent
RESULTS_DIR = TIER_DIR / "results"
REPORTS_DIR = TIER_DIR / "reports"
TABLES_DIR = RESULTS_DIR / "tables"
CONFIG_PATH = TIER_DIR / "config" / "00_refinement_config.yaml"
TIER1_DIR = ROOT / "tier1_quick_preview"
TIER1_ADATA = TIER1_DIR / "results" / "adata.preview.h5ad"
TIER1_TOP_MARKERS = TIER1_DIR / "results" / "tables" / "cluster_top_markers.csv"


def main() -> int:
    workflow_cfg, workflow_path = load_workflow_config()
    tier_cfg = read_yaml(CONFIG_PATH)
    cluster_key = resolve_global_value(workflow_cfg, "cluster_key", "leiden")
    unknown_label = (
        str(tier_cfg.get("refinement", {}).get("unknown_label", "")).strip()
        or resolve_global_value(workflow_cfg, "unknown_label", "Unknown")
    )

    if not TIER1_ADATA.exists():
        raise SystemExit("Tier 2 requires Tier 1 outputs. Run ./run.sh first or use ./run.sh --tier tier1.")

    adata = ad.read_h5ad(TIER1_ADATA)
    if cluster_key not in adata.obs.columns:
        raise SystemExit(f"Required cluster column not found in Tier 1 output: {cluster_key}")

    ensure_directory(TABLES_DIR)
    ensure_directory(REPORTS_DIR)

    marker_file = str(tier_cfg.get("refinement", {}).get("marker_file", "")).strip()
    refinement = (
        adata.obs[[cluster_key]]
        .groupby(cluster_key, dropna=False, observed=False)
        .size()
        .rename("n_cells")
        .reset_index()
        .assign(
            marker_file=marker_file or "",
            marker_support="not_run" if not marker_file else "planned",
            refined_broad_label=unknown_label,
            refinement_status="needs_marker_review",
            recommendation="Add marker evidence or proceed cautiously to Tier 3.",
        )
    )
    if TIER1_TOP_MARKERS.exists():
        top_markers = pd.read_csv(TIER1_TOP_MARKERS)
        top_markers["cluster"] = top_markers["cluster"].astype(str)
        top_marker_strings = (
            top_markers.groupby("cluster", observed=False)["gene"]
            .apply(lambda s: ", ".join(s.head(5).astype(str)))
            .rename("top_markers")
            .reset_index()
        )
        refinement[cluster_key] = refinement[cluster_key].astype(str)
        refinement = refinement.merge(top_marker_strings, how="left", left_on=cluster_key, right_on="cluster").drop(columns=["cluster"])
    else:
        refinement["top_markers"] = ""
    refinement["marker_file"] = refinement["marker_file"].fillna("")
    refinement["top_markers"] = refinement["top_markers"].fillna("")
    refinement.to_csv(TABLES_DIR / "refinement_suggestions.csv", index=False)

    marker_sets = load_marker_sets(marker_file)
    marker_summary, marker_long = score_marker_sets(adata, marker_sets, cluster_key=cluster_key)
    if marker_summary.empty:
        marker_summary = pd.DataFrame(
            {
                "cluster": refinement[cluster_key].astype(str),
                "label": [unknown_label] * len(refinement),
                "marker_score": [pd.NA] * len(refinement),
                "status": ["marker_file_missing" if not marker_file else "marker_no_overlap"] * len(refinement),
            }
        )
    else:
        marker_summary = marker_summary.rename(columns={"marker_suggested_label": "label"})
        marker_summary["status"] = "marker_scored"
    marker_long_out = marker_long if not marker_long.empty else marker_summary
    marker_summary.to_csv(TABLES_DIR / "marker_review_summary.csv", index=False)
    marker_long_out.to_csv(TABLES_DIR / "cluster_marker_candidates.csv", index=False)

    adata.obs["refined_broad_label"] = unknown_label
    adata.obs["refinement_status"] = "needs_marker_review"
    adata.uns["scrna_annotate_tier2_status"] = "scaffold_refinement_complete"
    adata.write_h5ad(RESULTS_DIR / "adata.refined.h5ad")

    report_payload = {
        "tier": "tier2_refinement",
        "status": "complete",
        "workflow_config": str(workflow_path),
        "input_h5ad": str(TIER1_ADATA),
        "cluster_key": cluster_key,
        "marker_file": marker_file,
        "summary": {
            "n_clusters": int(refinement[cluster_key].astype(str).nunique()),
            "marker_file_supplied": bool(marker_file),
            "marker_labels_scored": int(marker_long["label"].astype(str).nunique()) if not marker_long.empty else 0,
        },
        "next_step": "Provide marker evidence or proceed to Tier 3 only after choosing a formal method and a suitable reference.",
    }
    (RESULTS_DIR / "run_info.yaml").write_text(yaml.safe_dump(report_payload, sort_keys=False), encoding="utf-8")

    marker_status_html = "<p>No marker scores were produced.</p>"
    if not marker_long.empty:
        marker_lines = []
        for cluster, group in marker_long.groupby("cluster", observed=False):
            best = group.sort_values("marker_score", ascending=False).head(3)
            summary = ", ".join(f"{row.label}:{row.marker_score:.3f}" for row in best.itertuples())
            marker_lines.append(f"<li><strong>Cluster {cluster}</strong>: {summary}</li>")
        marker_status_html = "<ul>" + "".join(marker_lines[:12]) + "</ul>"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Tier 2 Refinement</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem auto; max-width: 900px; line-height: 1.5; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    code {{ background: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 4px; }}
    .box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }}
  </style>
</head>
<body>
  <h1>Tier 2 Refinement</h1>
  <p>This scaffold consumes Tier 1 outputs and prepares the rebuilt workflow for marker-backed review.</p>
  <div class="box">
    <h2>Current Status</h2>
    <p>Tier 2 completed in scaffold mode.</p>
    <p>Marker file supplied: <code>{marker_file or "none"}</code></p>
  </div>
  <div class="box">
    <h2>What Was Written</h2>
    <p>The refinement tables were created with conservative placeholder labels and explicit review-needed status.</p>
    <p>This tier now reads Tier 1 top markers and, when a marker file is provided, computes marker scores per cluster.</p>
  </div>
  <div class="box">
    <h2>Marker Evidence Preview</h2>
    {marker_status_html}
  </div>
  <div class="box">
    <h2>Recommended Next Step</h2>
    <p>Use Tier 3 only after you have chosen a formal method and confirmed that a relevant reference or model exists for your tissue and species.</p>
  </div>
</body>
</html>
"""
    (REPORTS_DIR / "02_refinement.html").write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
