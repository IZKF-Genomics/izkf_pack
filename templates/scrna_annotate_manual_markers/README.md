# scrna_annotate_manual_markers

Manual marker gene annotation template for scRNA-seq cluster review.

This template follows a simple marker program scoring workflow:

1. read a prepared `.h5ad`
2. read a user-defined marker gene list
3. score each marker program with `scanpy.tl.score_genes`
4. z-score marker scores across cells
5. assign each cluster to the marker program with the highest mean z-score
6. write standardized `annotation_result.json`, CSV/Excel outputs, an annotated `.h5ad`, and a Quarto report

The result JSON uses:

```text
schema_version = izkf_annotation_result.v1
```

## Run

Inside a project workspace, this automatically uses:

```text
../scrna_prep/results/adata.prep.h5ad
```

Run:

```bash
cd /path/to/project/scrna_annotate_manual_markers
bash run.sh
```

Explicit input:

```bash
INPUT_H5AD=/path/to/adata.prep.h5ad \
MARKER_CATALOG=config/marker_genes.csv \
CLUSTER_KEY=leiden \
./run.sh
```

## Marker List

Default:

```text
config/marker_genes.csv
```

Legacy format:

```csv
Hematopoietic stem cells,F10,feature_8692,Gene Expression
Hematopoietic stem cells,Gnaz,feature_10988,Gene Expression
```

Headered CSV/TSV is also supported with `cell_type` and `gene_symbol` columns.

## Outputs

```text
results/annotation_result.json
results/adata.annotated.h5ad
results/report.qmd
results/report.html
results/scrna_annotate_manual_markers_results.xlsx
results/tables/cluster_annotation_summary.csv
results/tables/manual_marker_scores.csv
results/tables/manual_marker_catalog.csv
results/tables/sample_composition.csv
results/tables/differential_markers.csv
```

The annotated H5AD adds:

```text
scrna_annotate_manual_markers_label
scrna_annotate_manual_markers_confidence
scrna_annotate_manual_markers_review_status
scrna_annotate_manual_markers_n_candidates
scrna_annotate_manual_markers_top_score
scrna_annotate_manual_markers_score_margin
scrna_annotate_manual_markers_matched_genes
```
