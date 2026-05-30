# scrna_annotate_audit

Cluster-level audit template for comparing annotation outputs from:

- `scrna_annotate_celltypist`
- `scrna_annotate_manual_markers`
- `scrna_annotate_sctype`
- `scrna_annotate_scanvi_reference`

The template reads provider `results/annotation_result.json` files, compares cluster labels,
summarizes confidence and marker evidence, creates a review table, helps choose a final project
UMAP, and writes final annotated h5ad and Loupe Browser outputs.

## Review Workflow

Run once to create the audit report and draft decision table:

```bash
pixi run python run.py
```

Review `results/report.html` and edit the generated draft table. Place the completed table at:

```text
config/final_annotation_decisions.csv
```

The HTML report includes a cluster review dashboard with progress tracking, bulk fill buttons
for provider labels, a next-cluster review button, browser-local draft saving, CSV download
fallback, and local API actions when opened through `run.sh`.

Review the UMAP Selection page before final export. Update:

```toml
[audit]
selected_umap_key = "X_umap_nn30_md0_5"
selected_umap_reason = "Best balances global lineage separation, sample mixing, and cluster readability for this project."
```

Run again to apply human decisions and write:

```text
results/adata.final_annotated.h5ad
results/adata.final_annotated.cloupe
results/audit_report_static.html
```

Final columns are written to `adata.obs` with the prefix `scrna_annotate_audit_`. The selected
UMAP is copied to `adata.obsm["X_umap"]` before h5ad and cloupe export.

The project export template publishes the full finalized audit bundle under
`3_Reports/scrna_annotate_audit/<template_basename>/`, including the static report, final h5ad,
optional cloupe, JSON provenance, and review tables.
