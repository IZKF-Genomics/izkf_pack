# scverse_scrna_annotate

This template creates an editable `scverse` / `scanpy` cell annotation workspace for single-cell RNA-seq data and renders a Quarto report that separates raw classifier predictions from cluster-level review decisions.

It follows the same Linkar pattern as the other analysis workspaces in this pack:

- `run.sh` is the user-facing launcher
- `run.py` contains the runtime orchestration and writes `config/project.toml` plus `results/run_info.yaml`
- `pixi.toml` defines the local Python/Quarto environment
- `annotation.qmd` contains the annotation and review workflow
- `assets/` stores static template-owned files such as the software-version spec
- `lib/` stores reusable Python helpers

## Layout

- `annotation.qmd`: report source and annotation workflow
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
- `annotation_method`
- `celltypist_model`
- `celltypist_mode`
- `celltypist_p_thres`
- `cluster_key`
- `batch_key`
- `condition_key`
- `sample_id_key`
- `sample_label_key`
- `majority_vote_min_fraction`
- `confidence_threshold`
- `unknown_label`
- `predicted_label_key`
- `final_label_key`
- `marker_file`

At least `input_h5ad`, `cluster_key`, and a relevant `celltypist_model` must be available before execution.

The default pack binding is expected to prefer the latest recorded `scverse_scrna_prep` output rather than the integration output, because CellTypist uses gene-level expression and is most robust when the input still contains the full feature space.

## Runtime Behavior

The launcher [run.sh](run.sh):

- creates the runtime config under `config/project.toml`
- records resolved parameters in `results/run_info.yaml`
- installs the template-local Pixi environment
- renders [annotation.qmd](annotation.qmd) to HTML
- writes `results/software_versions.json`

The notebook:

- loads a prepared or integrated single-cell `.h5ad`
- validates the review cluster column and optional metadata
- runs CellTypist label transfer on a log-normalized expression view of the data
- records per-cell predicted labels and confidence scores
- summarizes predictions by the configured cluster key
- optionally scores user-provided marker sets for review
- writes final labels conservatively, leaving unresolved clusters as `Unknown`
- writes `results/adata.annotated.h5ad` and a Quarto report under `reports/`

Best-practice constraints baked into the template:

- automated annotation is treated as a starting point rather than a final answer
- the raw predicted label, cluster-level suggestion, and final label remain separate
- unresolved or conflicting clusters are retained as `Unknown` instead of being silently forced
- optional marker review can be layered on top of classifier predictions

## Marker File Format

The optional `marker_file` should be YAML. Two simple formats are supported:

```yaml
T_cells:
  - CD3D
  - CD3E
B_cells:
  - MS4A1
  - CD79A
```

or

```yaml
T_cells:
  markers:
    - CD3D
    - CD3E
```

## Outputs

- `results/adata.annotated.h5ad`
- `results/tables/cell_annotation_predictions.csv`
- `results/tables/cluster_annotation_summary.csv`
- `results/tables/marker_review_summary.csv`
- `results/tables/annotation_status_summary.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/annotation.html`

## Test Command

```bash
cd templates/scverse_scrna_annotate
python3 test.py
```
