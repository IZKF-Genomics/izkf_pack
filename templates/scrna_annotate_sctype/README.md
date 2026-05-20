# scrna_annotate_sctype

ScType-focused scRNA-seq cluster annotation template for human and mouse data.

This template does one workflow:

1. read a prepared `.h5ad`
2. check that the organism is human or mouse
3. rank cluster markers with Scanpy
4. score clusters against ScType positive and negative marker sets
5. compare optional project-local marker evidence
6. write a standardized `annotation_result.json`
7. write CSV/Excel outputs, an annotated `.h5ad`, and a Quarto review report

The result JSON uses:

```text
schema_version = izkf_annotation_result.v1
```

and is intended to become the common result contract for annotation templates.

## Run

```bash
cd /home/ckuo/github/izkf_pack/templates/scrna_annotate_sctype

INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=mouse \
CLUSTER_KEY=leiden \
./run.sh
```

When the template is used inside a project workspace, `INPUT_H5AD` can be omitted if the standard
prep output exists:

```text
../scrna_prep/results/adata.prep.h5ad
```

In that case, `bash run.sh` uses the `scrna_prep` H5AD automatically.

Optional context:

```bash
TISSUE="Immune system" \
INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=human \
CLUSTER_KEY=leiden \
./run.sh
```

## Catalogs

The default primary catalog is:

```text
download:sctype
```

This downloads and converts the public ScType marker database:

```text
https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/ScTypeDB_full.xlsx
```

For offline smoke tests only:

```bash
PRIMARY_CATALOG=builtin:sctype_core ./run.sh
```

Project-local manual marker annotation is handled by the separate
`scrna_annotate_manual_markers` template.

## Outputs

```text
results/annotation_result.json
results/adata.annotated.h5ad
results/report.qmd
results/report.html
results/scrna_annotate_sctype_results.xlsx
results/tables/differential_markers.csv
results/tables/sctype_candidates.csv
results/tables/cluster_annotation_summary.csv
```

The annotated H5AD adds:

```text
scrna_annotate_sctype_label
scrna_annotate_sctype_confidence
scrna_annotate_sctype_review_status
scrna_annotate_sctype_n_candidates
scrna_annotate_sctype_top_score
scrna_annotate_sctype_matched_positive_genes
scrna_annotate_sctype_matched_negative_genes
```

## Design Boundary

This template is ScType-specific. It does not run reference mapping, Tabula Muris mapping,
CellTypist, Azimuth, or implicit ortholog conversion. Those should be separate annotation templates
that emit the same `annotation_result.json` schema.
