# Manual Marker Annotation Config

`config/marker_genes.csv` is the default editable marker list.

The legacy CSV format is supported:

```csv
cell type,gene symbol,feature id,feature type
```

Headered CSV/TSV files are also supported when they include columns such as:

```text
cell_type
gene_symbol
source
citation
evidence
```

Only positive marker programs are implemented in version 1. The runner computes one
`scanpy.tl.score_genes` score per cell type, z-scores each score across cells, and assigns each
cluster to the cell type with the highest mean z-score.

Rules:

- Keep one marker gene per row.
- Make sure gene symbols match `adata.var_names`.
- Use the same species gene-symbol convention as the input H5AD.
- Treat labels with small `score_margin` as review candidates.
