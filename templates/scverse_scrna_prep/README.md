# scverse_scrna_prep

This template creates an editable `scverse` / `scanpy` preprocessing workspace for single-cell RNA-seq data and renders a Quarto QC report.

It follows the same Linkar pattern as the other analysis workspaces in this pack:

- `run.sh` is the user-facing launcher
- `build_scrna_prep_inputs.py` writes the runtime `config/project.toml` and `results/run_info.yaml`
- `pixi.toml` defines the local Python/Quarto environment
- `00_qc.qmd` contains the preprocessing and report logic

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
- renders [00_qc.qmd](00_qc.qmd) to HTML
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

For `.h5ad` input, the workspace expects raw counts. If the object stores normalized values in `X`, provide raw counts in `adata.layers["counts"]` before running the template.

## Outputs

- `results/adata.prep.h5ad`
- `results/tables/*.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/00_qc.html`

## Test command

```bash
cd templates/scverse_scrna_prep
python3 test.py
```
