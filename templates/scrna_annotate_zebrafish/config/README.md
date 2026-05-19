# Zebrafish Annotation Config

`marker_catalog.tsv` is the main editable project-local file for this template.

The default run uses:

```text
download:zcl_2_marker_list
```

which downloads and converts the public ZCL 2.0 marker list:

```text
https://bis.zju.edu.cn/ZCL/data/zclmarkerlist.csv
```

For a whole-fish 3 dpf dataset, use ZCL 2.0 as the automatic baseline:

```bash
MARKER_CATALOG=download:zcl_2_marker_list ./run.sh
```

FishSCT is recommended as an additional project-local source, but it should be converted into the
same TSV schema first. Keep FishSCT-derived rows in `config/marker_catalog.tsv` or another explicit
project-local TSV so the exact marker source is reviewable.

Copy a built-in catalog before customizing it:

```bash
cp config/default_catalogs/zebrafish_core.tsv config/marker_catalog.tsv
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

Rules:

- Keep `species = zebrafish`.
- Use one marker gene per row.
- Make sure `gene_symbol` matches `adata.var_names`.
- Replace example rows and citations before interpreting labels biologically.
- Use `tissue` and `stage` when a marker is context-specific.
- Candidate labels are filtered by hypergeometric enrichment with BH/FDR correction, not by a
  minimum matched-gene count.
