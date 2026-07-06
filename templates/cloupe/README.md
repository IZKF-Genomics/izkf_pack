# Loupe Browser export

`cloupe` converts an existing H5AD file into a 10x Genomics Loupe Browser `.cloupe`
file. It is intentionally separate from analysis templates because Loupe export depends
on LoupePy and the 10x Genomics converter setup/EULA.

Typical direct use:

```bash
cd /home/ckuo/github/izkf_pack/templates/cloupe
bash run.sh /path/to/adata.h5ad
```

The template reads the H5AD in place and writes next to the input file:

- `/path/to/adata.cloupe`
- `/path/to/adata_export.json`

Use `--output` or `OUTPUT_CLOUPE` to choose a different `.cloupe` path:

```bash
bash run.sh /path/to/adata.h5ad --output /path/to/custom.cloupe
```

For non-10x protocols such as PIPseq, Loupe's converter may reject the original
cell IDs as non-10x barcodes. Use export-only synthetic 10x-compatible barcodes
and retain the original IDs as Loupe metadata:

```bash
linkar run cloupe \
  --input /path/to/adata.h5ad \
  --counts-layer counts \
  --embedding-key X_umap \
  --barcode-mode synthetic_10x \
  --refresh \
  --verbose
```

## Configuration

Edit `config/export.toml`, pass command-line options, or override values with environment
variables.

```toml
[input]
h5ad = ""

[export]
output_cloupe = ""
metadata_json = ""
counts_layer = "counts"
embedding_key = "X_umap"
obs_keys = ""
barcode_mode = "original"
barcode_whitelist = ""
original_barcode_key = "original_cell_id"
synthetic_barcode_key = "loupe_synthetic_barcode"
```

`obs_keys` is a comma-separated list of `adata.obs` columns to export. Leave it empty,
or set it to `*`, to export all Loupe-compatible obs columns. Loupe metadata is
categorical, so columns with more than 32,768 distinct values are skipped with a warning.

Useful environment overrides are `INPUT_H5AD`, `OUTPUT_CLOUPE`, `METADATA_JSON`,
`COUNTS_LAYER`, `EMBEDDING_KEY`, `OBS_KEYS`, `BARCODE_MODE`, `BARCODE_WHITELIST`,
`ORIGINAL_BARCODE_KEY`, and `SYNTHETIC_BARCODE_KEY`.

## LoupePy setup

If the template reports that LoupePy converter setup is missing, review the 10x Genomics
terms and run the setup once inside this template workspace:

```bash
pixi run python -c "import loupepy; loupepy.setup()"
```

The setup is kept here so accepting the EULA is an explicit export decision rather than
a hidden step in a biological analysis pipeline.
