# Marker Catalogs

This directory contains local marker catalog TSV files consumed by the `marker_catalog` provider.

Catalogs are organism-aware resources. A catalog must not be applied to another organism unless a
future provider explicitly records an ortholog mapping source, version, and checksum.

## TSV Schema

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

Rules:

- `species` must match the dataset organism after normalization.
- `organism_id` should use NCBI Taxonomy when possible, for example `NCBITaxon:7955`.
- `gene_symbol` should match the gene symbols used in the `.h5ad`.
- `citation` should be filled for real catalogs.
- Keep one gene per row.

## Zebrafish

Start by copying the example file:

```bash
cp config/marker_catalogs/zebrafish.example.tsv config/marker_catalogs/zebrafish.local.tsv
```

Then replace the example rows with curated project markers and citations.

Run with:

```bash
ORGANISM=zebrafish \
MARKER_CATALOG_ENABLED=true \
MARKER_CATALOG_PATH=config/marker_catalogs/zebrafish.local.tsv \
MARKER_CATALOG_SPECIES=zebrafish \
./run.sh
```

## Future Downloaded Catalogs

Downloaded catalogs should be converted into this TSV schema before annotation. The download layer
should live outside project results and use:

```text
SCRNA_ANNOTATE_CACHE_DIR
```

If the variable is not set, use:

```text
~/.cache/izkf_pack/scrna_annotate/catalogs
```

Every downloaded or converted catalog should record:

- resource id
- source URL
- source version/release
- local cached path
- SHA256 checksum
- conversion script/version
- species/organism id
- citation

The provider should consume the resolved TSV and record the checksum in `annotation_result.json`.
