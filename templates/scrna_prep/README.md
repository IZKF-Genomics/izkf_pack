# scrna_prep

This template creates an editable `scverse` / `scanpy` preprocessing workspace for single-cell RNA-seq data and renders a Quarto QC report.

It follows the same Linkar pattern as the other analysis workspaces in this pack:

- `run.sh` is the user-facing launcher
- `run.py` contains the runtime orchestration and writes `config/project.toml` plus `results/run_info.yaml`
- `pixi.toml` defines the local Python/Quarto environment
- `scrna_prep.qmd` contains the preprocessing and report logic
- `assets/` stores static template fixtures such as the sample metadata stub and software-version spec
- `lib/` stores notebook helper code

## Layout

- `scrna_prep.qmd`: report source and preprocessing workflow
- `assets/`: static template-owned files checked into git
- `config/`: runtime-generated project config
- `lib/`: reusable Python helpers imported by the notebook
- `run.py`: main execution logic
- `run.sh`: thin launcher kept for the Linkar entrypoint
- `test.py`: template-local verification

## Linkar interface

Important parameters:

- `input_h5ad`
- `input_matrix`
- `input_format`
- `sample_metadata`
- `organism`
- `batch_key`
- `condition_key`
- `sample_id_key`
- `doublet_method`
- `filter_predicted_doublets`
- `qc_mode`
- `qc_nmads`
- `min_genes`
- `min_cells`
- `min_counts`
- `max_pct_counts_mt`
- `max_pct_counts_ribo`
- `max_pct_counts_hb`
- `n_top_hvgs`
- `n_pcs`
- `n_neighbors`
- `leiden_resolution`
- `resolution_grid`

At least one of `input_h5ad` or `input_matrix` must be set before execution, and `organism` must be provided for QC gene annotation.

When `sample_metadata` is not provided, the template defaults to `assets/samples.csv`.

With `--binding default`, the pack can resolve these values automatically from the latest recorded `nfcore_scrnaseq` run when present:

- `input_h5ad` from `selected_matrix_h5ad`
- `input_source_template` from the upstream template id
- `ambient_correction_applied` and `ambient_correction_method` from the selected matrix filename
- `organism` from the upstream genome metadata

## Runtime behavior

The launcher [run.sh](run.sh):

- creates the runtime config under `config/project.toml`
- records resolved parameters in `results/run_info.yaml`
- installs the template-local Pixi environment
- renders [scrna_prep.qmd](scrna_prep.qmd) to HTML
- writes `results/software_versions.json`

The notebook supports:

- direct `.h5ad` input
- 10x HDF5 and MTX inputs
- ParseBio directory inputs
- ScaleBio / STARsolo-style MTX inputs
- Cell Ranger `per_sample_outs` directories
- fixed-threshold QC and per-sample MAD-based QC
- optional Scrublet-based doublet scoring
- PCA, neighbors, UMAP, Leiden clustering, and resolution benchmarking

DRAGEN-produced count matrices can be passed to this template directly without
running `nfcore_scrnaseq` first. For vendor-processed Illumina Single Cell 3'
RNA Prep projects, prefer explicit `input_format` values such as `10x_h5` or
`10x_mtx` instead of relying on `auto` detection when pointing `input_matrix`
to the DRAGEN output.

For `.h5ad` input, the workspace expects raw counts. If the object stores normalized values in `X`, provide raw counts in `adata.layers["counts"]` before running the template.

QC gene annotation expects gene symbols for mitochondrial / ribosomal / hemoglobin labeling. When using `var_names=gene_ids`, keep gene symbols available in a recognized `adata.var` column such as `gene_symbols` or `gene_name`.

Current limitation: QC gene-prefix annotation in this template is implemented
for human and mouse aliases only. Handoffs from upstream genomes such as
zebrafish (`drerio` / `GRCz11`) can still supply the expression matrix, but the
QC report may require a small template update before gene-family labeling works
cleanly for that organism.

## Outputs

- `results/adata.prep.h5ad`
- `results/tables/*.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/scrna_prep.html`

## Test command

```bash
cd templates/scrna_prep
python3 test.py
```
