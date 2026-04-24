# scrna_prep

This template creates an editable `scverse` / `scanpy` preprocessing workspace for single-cell RNA-seq data and renders a Quarto QC report.

It follows the same Linkar pattern as the other analysis workspaces in this pack:

- `run.sh` is the user-facing launcher and shows the main shell steps explicitly
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
- `run.sh`: explicit launcher kept for the Linkar entrypoint
- `test.py`: template-local verification

## Input Model

The template accepts exactly one primary input path:

- `input_h5ad`
  Use this only for an existing AnnData `.h5ad` file.
- `input_matrix`
  Use this for matrix-style inputs such as Cell Ranger `.h5`, 10x MTX directories, ParseBio outputs, ScaleBio outputs, or Cell Ranger `per_sample_outs`.

Key rules:

- Set exactly one of `input_h5ad` or `input_matrix`.
- Set `organism` for QC gene annotation.
- Leave `sample_metadata` empty unless you have a real CSV file to provide.
- Keep `input_format=auto` for obvious `.h5ad`, `.h5`, or standard output directories.
- Prefer an explicit `input_format` for vendor-specific or ambiguous directories such as DRAGEN exports.

Parameter behavior:

- `input_source_template`, `ambient_correction_applied`, and `ambient_correction_method` are provenance fields. They are recorded in the report but do not change how the input is read.
- `var_names` matters for MTX-style inputs. It is ignored for `.h5ad` and 10x `.h5`.
- `filter_predicted_doublets=true` only makes sense with `doublet_method=scrublet`.
- `qc_nmads` is only used when `qc_mode=mad_per_sample`.
- When `sample_metadata` is omitted, the workspace uses `assets/samples.csv`.

With `--binding default`, the pack can resolve these values automatically from the latest recorded `nfcore_scrnaseq` run when present:

- `input_h5ad` from `selected_matrix_h5ad`
- `input_source_template` from the upstream template id
- `ambient_correction_applied` and `ambient_correction_method` from the selected matrix filename
- `organism` from the upstream genome metadata

## Examples

Minimal `.h5ad` handoff:

```bash
linkar render scrna_prep \
  --input-h5ad /path/to/adata.raw_counts.h5ad \
  --organism mouse
```

10x / Cell Ranger HDF5:

```bash
linkar render scrna_prep \
  --input-matrix /path/to/filtered_feature_bc_matrix.h5 \
  --input-format 10x_h5 \
  --organism human
```

10x MTX directory:

```bash
linkar render scrna_prep \
  --input-matrix /path/to/filtered_feature_bc_matrix \
  --input-format 10x_mtx \
  --organism human
```

ParseBio directory:

```bash
linkar render scrna_prep \
  --input-matrix /path/to/parsebio_run \
  --input-format parsebio \
  --organism mouse
```

ScaleBio or STARsolo-style MTX directory:

```bash
linkar render scrna_prep \
  --input-matrix /path/to/scalebio_counts \
  --input-format scalebio \
  --organism mouse \
  --var-names gene_symbols
```

Cell Ranger `per_sample_outs` directory:

```bash
linkar render scrna_prep \
  --input-matrix /path/to/per_sample_outs \
  --input-format cellranger_per_sample_outs \
  --organism human
```

Optional sample metadata CSV:

```bash
linkar render scrna_prep \
  --input-matrix /path/to/filtered_feature_bc_matrix.h5 \
  --input-format 10x_h5 \
  --sample-metadata /path/to/sample_metadata.csv \
  --organism human
```

Automatic handoff from `nfcore_scrnaseq` with default binding:

```bash
linkar render scrna_prep --binding default
```

The binding case works best when an upstream `nfcore_scrnaseq` run already published `selected_matrix_h5ad` and organism metadata.

## Input-Specific Notes

For `.h5ad` input, the workspace expects raw counts. If the object stores normalized values in `X`, provide raw counts in `adata.layers["counts"]` before running the template.

For 10x `.h5` input, `scanpy.read_10x_h5()` defines the feature names, so `var_names` has no effect.

For MTX-style inputs, use `var_names=gene_symbols` when possible. QC gene annotation still requires gene symbols, either as feature names or in a recognized `adata.var` column such as `gene_symbols` or `gene_name`.

DRAGEN-produced count matrices can be passed to this template directly without running `nfcore_scrnaseq` first. For vendor-processed Illumina Single Cell 3' RNA Prep projects, prefer explicit `input_format` values such as `10x_h5` or `10x_mtx` instead of relying on `auto`.

Current limitation: QC gene-prefix annotation in this template is implemented for human and mouse aliases only. Handoffs from upstream genomes such as zebrafish (`drerio` / `GRCz11`) can still supply the expression matrix, but the QC report may require a small template update before gene-family labeling works cleanly for that organism.

## Runtime Behavior

The launcher [run.sh](run.sh):

- creates the runtime config under `config/project.toml`
- records resolved parameters in `results/run_info.yaml`
- runs `pixi install`
- runs `pixi run quarto render scrna_prep.qmd --to html --output-dir reports --no-clean`
- writes `results/software_versions.json`

Internally, [run.py](run.py) supports `--prepare-only` so the shell launcher can show the execution steps explicitly while still centralizing validation and runtime config generation in Python.

The notebook supports:

- direct `.h5ad` input
- 10x HDF5 and MTX inputs
- ParseBio directory inputs
- ScaleBio / STARsolo-style MTX inputs
- Cell Ranger `per_sample_outs` directories
- fixed-threshold QC and per-sample MAD-based QC
- optional Scrublet-based doublet scoring
- PCA, neighbors, UMAP, Leiden clustering, and resolution benchmarking

## Outputs

- `results/adata.prep.h5ad`
- `results/tables/*.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/scrna_prep.html`

## Test Command

```bash
cd templates/scrna_prep
python3 test.py
```
