# Loupe Browser export

`cloupe` converts an existing H5AD file into a 10x Genomics Loupe Browser `.cloupe`
file. It is intentionally separate from analysis templates because Loupe export depends
on LoupePy and the 10x Genomics converter setup/EULA.

Typical use after zebrafish annotation:

```bash
linkar run cloupe --input scrna_annotate_zebrafish/results/adata.annotated.h5ad
```

The template reads the H5AD in place and writes:

- `results/output.cloupe`
- `results/cloupe_export.json`

## Configuration

Edit `config/export.toml` after rendering, or override values with environment variables.

```toml
[input]
h5ad = ""

[export]
counts_layer = "counts"
embedding_key = "X_umap"
obs_keys = ""
```

`obs_keys` is a comma-separated list of additional `adata.obs` columns to export.
Common columns are detected automatically when present, including sample id, cluster id,
zebrafish annotation label, confidence, review status, treatment, and genotype.

## LoupePy setup

If the template reports that LoupePy converter setup is missing, review the 10x Genomics
terms and run the setup once inside this template workspace:

```bash
pixi run python -c "import loupepy; loupepy.setup()"
```

The setup is kept here so accepting the EULA is an explicit export decision rather than
a hidden step in a biological analysis pipeline.
