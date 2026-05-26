# scrna_annotate_audit

Cluster-level audit template for comparing annotation outputs from:

- `scrna_annotate_celltypist`
- `scrna_annotate_manual_markers`
- `scrna_annotate_sctype`
- `scrna_annotate_scanvi_reference`

The template reads provider `results/annotation_result.json` files, compares cluster labels,
summarizes confidence and marker evidence, creates a review table, and writes a final annotated
h5ad.

## Review Workflow

Run once to create the audit report and draft decision table:

```bash
pixi run python run.py
```

Review `results/report.html` and edit the generated draft table. Place the completed table at:

```text
config/final_annotation_decisions.csv
```

Run again to apply human decisions and write:

```text
results/adata.final_annotated.h5ad
```

Final columns are written to `adata.obs` with the prefix `scrna_annotate_audit_`.
