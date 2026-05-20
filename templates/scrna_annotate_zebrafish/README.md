# scrna_annotate_zebrafish

Focused zebrafish scRNA-seq annotation template.

This template intentionally avoids the generic provider architecture. It does one workflow:

1. read a prepared `.h5ad`
2. check that the organism is zebrafish/Danio rerio
3. rank cluster markers with Scanpy
4. test cluster marker enrichment against an explicit zebrafish marker catalog
5. write CSV/JSON/Excel outputs and an annotated `.h5ad`
6. render a Quarto review report

It is meant for practical zebrafish testing and report iteration. Once the catalog schema and
reporting behavior are stable, the logic can be promoted back into the generic `scrna_annotate`
provider architecture.

## Run

```bash
cd /home/ckuo/github/izkf_pack/templates/scrna_annotate_zebrafish

INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=zebrafish \
CLUSTER_KEY=leiden \
./run.sh
```

Optional context:

```bash
TISSUE=brain \
STAGE=larval \
INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=zebrafish \
CLUSTER_KEY=leiden \
./run.sh
```

Optional statistical threshold:

```bash
FDR_THRESHOLD=0.05 \
INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=zebrafish \
CLUSTER_KEY=leiden \
./run.sh
```

## Outputs

```text
results/annotation_result.json
results/adata.annotated.h5ad
results/report.qmd
results/report.html
results/scrna_annotate_zebrafish_results.xlsx
results/tables/differential_markers.csv
results/tables/catalog_matches.csv
results/tables/cluster_annotation_summary.csv
```

The annotated H5AD is written by default and adds review columns to `adata.obs`, including:

```text
scrna_annotate_zebrafish_label
scrna_annotate_zebrafish_confidence
scrna_annotate_zebrafish_review_status
scrna_annotate_zebrafish_n_candidates
scrna_annotate_zebrafish_top_score
scrna_annotate_zebrafish_matched_genes
scrna_annotate_zebrafish_treatment
scrna_annotate_zebrafish_genotype
```

## Loupe Browser Export

Loupe Browser export is intentionally handled by the separate `cloupe` template because it depends
on `loupepy`, the 10x Genomics Loupe converter setup, and EULA acceptance. Use the annotated H5AD
from this template as the input to `cloupe`.

Example:

```bash
linkar run cloupe --input scrna_annotate_zebrafish/results/adata.annotated.h5ad
```

## Marker Catalog

By default the template uses:

```text
download:zcl_2_marker_list
```

This downloads the ZCL 2.0 marker list and converts it into the template marker catalog schema.
ZCL 2.0 is the best current default for whole-fish, 3 dpf-style annotation because it is a
zebrafish single-cell landscape resource and includes 72 hpf context.

Run explicitly:

```text
MARKER_CATALOG=download:zcl_2_marker_list ./run.sh
```

The small built-in catalog remains available as `builtin:zebrafish_core` for offline smoke tests
only. Do not use it for biological interpretation.

## Download a Catalog

The downloadable catalog supported by code is:

```text
download:zcl_2_marker_list
```

It downloads the public ZCL 2.0 marker list and converts cluster/cell-type marker rows into the
template marker catalog schema.

Run:

```bash
INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=zebrafish \
CLUSTER_KEY=leiden \
MARKER_CATALOG=download:zcl_2_marker_list \
./run.sh
```

Downloaded catalogs are cached under:

```text
SCRNA_ANNOTATE_CATALOG_CACHE
```

If that variable is not set:

```text
~/.cache/izkf_pack/scrna_annotate_zebrafish/catalogs
```

Refresh explicitly:

```bash
REFRESH_CATALOG=true MARKER_CATALOG=download:zcl_2_marker_list ./run.sh
```

For a project-specific FishSCT-derived catalog, create or copy:

```text
config/marker_catalog.tsv
```

Then run with:

```bash
MARKER_CATALOG=config/marker_catalog.tsv ./run.sh
```

Required columns:

```text
catalog_id
species
organism_id
tissue
stage
cell_type
gene_symbol
source
citation
evidence
```

The bundled built-in catalog is a starter fixture. Replace it with curated zebrafish markers before
interpreting labels biologically. If Linkar resolves the default to a missing project-level
`config/marker_catalog.tsv`, the runner falls back to `builtin:zebrafish_core` and records a warning.

Catalog candidates are selected with a hypergeometric marker-set enrichment test followed by
Benjamini-Hochberg FDR correction within each cluster. `n_matched` is reported as evidence, but it is
not used as a hard filter.

For your whole-fish, 3 dpf data, the recommended source order is:

1. `download:zcl_2_marker_list` as the automatic baseline.
2. A project-local FishSCT-derived TSV for additional curated markers from relevant datasets.
3. Project/literature expert markers for labels that remain ambiguous.

Keep one marker gene per row and make sure `gene_symbol` matches `adata.var_names`.

## Catalog Source Options

Possible zebrafish catalog/reference sources:

| Source | Best use | Current status |
| --- | --- | --- |
| ZCL 2.0 marker list | Whole-fish and multi-stage zebrafish single-cell marker baseline | supported as `download:zcl_2_marker_list`; default |
| FishSCT | Fish/zebrafish single-cell marker database | recommended as project-local TSV until a stable bulk endpoint is wired |
| Project/local TSV | Best path for curated FishSCT/literature markers | supported |
| Built-in `zebrafish_core` | Offline smoke tests only | bundled |
| ZMAP | Embryonic zebrafish reference atlas and marker programs | future reference/catalog importer |
| BASiCz | Zebrafish blood/hematopoietic atlas | future domain-specific importer |
| mapzebrain | Larval zebrafish brain atlas | future brain-specific reference importer |
| DRscDB | Cross-species scRNA resource with ortholog context | future explicit ortholog-aware workflow only |

The clean rule is: downloadable resources should be converted to the local TSV schema before
annotation, and cross-species resources should not be applied without explicit ortholog provenance.

## Design Boundary

This template is zebrafish-specific. It does not apply human marker signatures, mouse catalogs, or
implicit ortholog mapping. Cross-species resources should be handled by a separate explicit
ortholog-mapped workflow with recorded provenance.
