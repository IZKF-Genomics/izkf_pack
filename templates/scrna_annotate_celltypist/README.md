# scrna_annotate_celltypist

CellTypist-focused scRNA-seq annotation template.

This template:

1. reads a prepared `.h5ad`
2. queries the CellTypist model API for the current model index
3. downloads an explicit model or selects one with `model = "auto"`
4. optionally converts human/mouse models with CellTypist's built-in ortholog mapping
5. runs CellTypist prediction and optional majority voting
6. writes the shared `annotation_result.json` schema, tables, an annotated `.h5ad`, and a Quarto HTML report

## Typical use

```bash
linkar run scrna_annotate_celltypist \
  --organism mouse \
  --tissue heart \
  --model auto
```

With the default binding, `input_h5ad` resolves from the latest `scrna_prep` output. Direct
`./run.sh` execution also falls back to `../scrna_prep/results/adata.prep.h5ad` when `INPUT_H5AD`
is unset.

For `model = "auto"`, model selection is tissue-first within a conservative species policy:

1. use a matching-species tissue model when available
2. otherwise use a human/mouse cross-species tissue model and convert it when `convert_model = "auto"`
3. otherwise fall back to a matching-species general model

For example, a mouse heart query will prefer a native mouse heart model; if none is available but a
human heart model is available, the human heart model is converted to mouse orthologs and the report
records a cross-species review warning.

For cross-species use, the template records a warning:

```toml
[celltypist]
model = "auto"
model_species = "auto"
convert_model = "auto"
```

If a human model is selected for mouse data, CellTypist's `Model.convert()` is used automatically for human/mouse pairs when `convert_model` is `auto` or `true`.

## Outputs

```text
results/annotation_result.json
results/adata.annotated.h5ad
results/report.html
results/report.qmd
results/tables/celltypist_available_models.csv
results/tables/celltypist_predictions.csv
results/tables/celltypist_label_summary.csv
results/tables/celltypist_cluster_summary.csv
```

The annotated `.h5ad` contains method-specific columns:

```text
scrna_annotate_celltypist_label
scrna_annotate_celltypist_confidence
scrna_annotate_celltypist_predicted_label
scrna_annotate_celltypist_majority_label
scrna_annotate_celltypist_score
```
