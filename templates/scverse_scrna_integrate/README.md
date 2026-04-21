# scverse_scrna_integrate

This template creates an editable `scverse` / `scanpy` single-cell RNA-seq integration workspace and renders a Quarto report that compares the unintegrated baseline with the integrated result.

It follows the same Linkar pattern as the other analysis workspaces in this pack:

- `run.sh` is the user-facing launcher
- `run.py` contains the runtime orchestration and writes `config/project.toml` plus `results/run_info.yaml`
- `pixi.toml` defines the local Python/Quarto environment
- `qc.qmd` contains the integration and evaluation workflow
- `assets/` stores static template-owned files such as the software-version spec
- `lib/` stores reusable Python helpers

## Layout

- `qc.qmd`: report source and integration workflow
- `assets/`: static template-owned files checked into git
- `config/`: runtime-generated project config
- `lib/`: reusable Python helpers imported by the notebook
- `run.py`: main execution logic
- `run.sh`: thin launcher kept for the Linkar entrypoint
- `test.py`: template-local verification

## Linkar Interface

Important parameters:

- `input_h5ad`
- `input_source_template`
- `integration_method`
- `batch_key`
- `condition_key`
- `sample_id_key`
- `sample_label_key`
- `label_key_for_metrics`
- `run_scib_metrics`
- `use_hvgs_only`
- `n_top_hvgs`
- `n_pcs`
- `n_neighbors`
- `umap_min_dist`
- `cluster_resolution`
- `random_seed`
- `scanvi_label_key`
- `scanvi_unlabeled_category`
- `scvi_latent_dim`
- `scvi_max_epochs`
- `scvi_gene_likelihood`

At least `input_h5ad` and a real `batch_key` must be available before execution. If the configured batch column is missing or contains only one real category, the run fails instead of fabricating placeholder batches.

With the default pack binding, `input_h5ad` and `input_source_template` can resolve automatically from the latest recorded `scverse_scrna_prep` run.

## Runtime Behavior

The launcher [run.sh](run.sh):

- creates the runtime config under `config/project.toml`
- records resolved parameters in `results/run_info.yaml`
- installs the template-local Pixi environment
- renders [qc.qmd](qc.qmd) to HTML
- writes `results/software_versions.json`

The notebook:

- loads a prep-stage `.h5ad`
- validates the batch and metadata columns
- computes an unintegrated baseline PCA/UMAP/Leiden view before correction
- runs one integration backend: `scvi`, `scanvi`, `harmony`, `bbknn`, or `scanorama`
- rebuilds neighbors, UMAP, and Leiden clustering from the integrated representation
- computes quantitative integration diagnostics, including batch-mixing summaries and optional scIB metrics
- writes `results/adata.integrated.h5ad` and a Quarto report under `reports/`

Best-practice constraints baked into the template:

- the unintegrated baseline is always shown before correction
- `scvi` and `scanvi` require `adata.layers["counts"]`
- `scanvi` requires an explicit label column
- batch metadata are validated rather than silently invented
- quantitative evaluation is produced in addition to embedding plots

## Outputs

- `results/adata.integrated.h5ad`
- `results/tables/integration_summary.csv`
- `results/tables/integration_metrics.csv`
- `results/tables/batch_mixing_summary.csv`
- `results/tables/cluster_counts.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/qc.html`

## Test Command

```bash
cd templates/scverse_scrna_integrate
python3 test.py
```
