# ercc

Editable ERCC spike-in QC workspace for Linkar projects.

## Inputs

- Salmon quant directory containing `salmon.merged.gene_tpm.tsv`
- nf-core-style samplesheet CSV with a `sample` column
- optional author string for the report header

## Render

```bash
linkar render ercc --outdir ./ercc
```

Optional overrides:

```bash
linkar render ercc \
  --salmon-dir /path/to/salmon \
  --samplesheet /path/to/samplesheet.csv \
  --authors "Author One, Author Two" \
  --outdir ./ercc
```

When rendered inside a project, the default pack bindings can reuse the same upstream
RNA-seq outputs as `dgea` for `salmon_dir`, `samplesheet`, and `authors`.

## Run

```bash
linkar run ercc --outdir ./ercc --verbose
```

Or from the rendered folder:

```bash
bash run.sh
```

## Outputs

- `results/ERCC.html`: rendered QC report
- `results/ERCC_files/`: Quarto support assets when present
- `results/run_info.yaml`: resolved input metadata
- `results/software_versions.json`: captured Pixi, Quarto, and R versions

## Notes

- The run writes `ercc_inputs.R` and `ERCC.runtime.qmd` so the report uses resolved
  absolute paths instead of Jinja-time placeholders.
- The report validates that `salmon.merged.gene_tpm.tsv` exists, the samplesheet
  contains a `sample` column, and every listed sample appears in the merged TPM table.
