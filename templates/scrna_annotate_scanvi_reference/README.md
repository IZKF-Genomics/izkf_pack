# scrna_annotate_scanvi_reference

scVI/scANVI reference label-transfer template for scRNA-seq annotation.

This template:

1. reads a prepared query `.h5ad`
2. reads a labeled reference `.h5ad`, such as Tabula Muris, GSE230531, or a custom atlas
3. optionally filters the reference by tissue
4. intersects query/reference genes
5. trains an scVI latent model
6. converts the model to scANVI using reference labels and query `Unknown` labels
7. predicts query labels with probabilities
8. writes the shared `annotation_result.json` schema, tables, an annotated `.h5ad`, and a Quarto HTML report

## Typical Use

```bash
REFERENCE_H5AD=/path/to/reference.h5ad \
REFERENCE_NAME=tabula_muris \
REFERENCE_LABEL_KEY=cell_ontology_class \
REFERENCE_TISSUE_KEY=tissue \
REFERENCE_TISSUE_FILTER=Heart \
COUNTS_LAYER=counts \
./run.sh
```

With the default binding, `input_h5ad` resolves from the latest `scrna_prep` output. Direct
`./run.sh` execution also falls back to `../scrna_prep/results/adata.prep.h5ad` when `INPUT_H5AD`
is unset.

## Important Assumptions

- `counts_layer` should contain raw counts or count-like UMI values. Use `COUNTS_LAYER=X` only if
  `.X` contains raw counts.
- The reference must already have trustworthy labels in `reference_label_key`.
- Tabula Muris is best used as a coarse lineage sanity reference. For cardiac subtypes or disease
  states, prefer a matched mouse heart reference.
- Low-confidence query predictions and clusters with mixed transferred labels should be audited
  against marker genes instead of accepted automatically.

## Outputs

```text
results/annotation_result.json
results/adata.annotated.h5ad
results/report.qmd
results/report.html
results/tables/scanvi_cell_predictions.csv
results/tables/scanvi_label_summary.csv
results/tables/scanvi_cluster_summary.csv
results/tables/scanvi_reference_summary.csv
results/tables/scanvi_training_metrics.csv
```

The annotated `.h5ad` contains:

```text
scrna_annotate_scanvi_reference_label
scrna_annotate_scanvi_reference_confidence
scrna_annotate_scanvi_reference_probability
scrna_annotate_scanvi_reference_entropy
scrna_annotate_scanvi_reference_review_status
scrna_annotate_scanvi_reference_candidate_1
scrna_annotate_scanvi_reference_candidate_1_probability
scrna_annotate_scanvi_reference_candidate_2
scrna_annotate_scanvi_reference_candidate_2_probability
scrna_annotate_scanvi_reference_candidate_3
scrna_annotate_scanvi_reference_candidate_3_probability
```
