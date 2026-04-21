# scverse_scrna_annotate

`scverse_scrna_annotate` creates an editable Python-only `scverse` / `scanpy`
workspace for scRNA-seq cell annotation review. It currently implements
`CellTypist` as the production backend, keeps marker review optional, and
renders one shared overview report plus method-specific sub-reports.

The design follows the single-cell best-practices guidance that automated
annotation should be treated as a starting point, not as final truth:

- keep per-cell predictions separate from cluster-level suggestions
- keep final labels separate from automated labels
- preserve unresolved clusters as `Unknown`
- support marker-based review instead of silently overriding classifier output

Reference:
- Single-cell best practices, annotation chapter:
  <https://www.sc-best-practices.org/cellular_structure/annotation.html>

## Python-only scope

This template is intentionally kept Python-only.

- Included now: `CellTypist`
- Planned Python candidates: `scANVI`, `decoupler` review, `scGPT`
- Explicitly out of scope for this template: `scmap` and `scPred`, because
  they are R/Bioconductor-centered tools and would complicate the runtime
  environment

That keeps `run.sh`, `pixi`, and the exported workspace easier to maintain.

## Layout

- `run.sh`: user-facing launcher
- `run.py`: runtime orchestration
- `assets/annotation_config.template.yaml`: commented user config template
- `config/annotation_config.yaml`: working copy created automatically on first run
- `config/project.toml`: internal runtime config generated from YAML/env values
- `config/annotation_config.resolved.yaml`: resolved config used for the run
- `build_annotation_outputs.py`: shared annotation pipeline executed once
- `annotation_overview.qmd`: cross-method review report
- `celltypist.qmd`: CellTypist-specific diagnostic report
- `lib/`: reusable Python helpers
- `results/`: generated tables, H5AD output, and metadata
- `reports/`: rendered HTML reports

## Quick Start

1. Open `config/annotation_config.yaml`.
   If it does not exist yet, run `./run.sh` once and the template will seed it
   from `assets/annotation_config.template.yaml`.
2. Fill in at least:
   - `global.input_h5ad`
   - `celltypist.model`
   - `global.cluster_key` if your clustering column is not `leiden`
3. Optionally set `marker_review.marker_file`.
4. Run:

```bash
./run.sh
```

5. Inspect:
   - `reports/annotation_overview.html`
   - `reports/celltypist.html`
   - `results/adata.annotated.h5ad`

Environment variables still work and override YAML values. That makes the
template compatible with Linkar bindings while still giving users a readable
config file for local reruns.

## Required inputs

At minimum the run needs:

- an input `.h5ad` object
- a cluster column in `adata.obs`
- a suitable CellTypist model
- a precomputed `X_umap` embedding in the input object

Recommended upstream source:

- prefer `scverse_scrna_prep` output when possible, because classifier-based
  annotation benefits from the full gene feature space
- use `scverse_scrna_integrate` output only when you intentionally want to
  annotate an integrated object and the feature representation is still suitable
  for the classifier

## YAML config structure

The user-facing config is organized into three sections:

- `global`: input paths, metadata keys, review thresholds, output label keys
- `celltypist`: backend-specific settings
- `marker_review`: optional marker gene file

The shipped template already includes comment lines for every current key and
its expected values:

- [assets/annotation_config.template.yaml](assets/annotation_config.template.yaml)

Example:

```yaml
global:
  input_h5ad: /abs/path/to/adata.prep.h5ad
  input_source_template: scverse_scrna_prep
  annotation_method: celltypist
  annotation_methods:
    - celltypist
  cluster_key: leiden
  batch_key: batch
  condition_key: condition
  sample_id_key: sample_id
  sample_label_key: sample_display
  majority_vote_min_fraction: 0.6
  confidence_threshold: 0.5
  unknown_label: Unknown
  predicted_label_key: predicted_label
  final_label_key: final_label
  rank_top_markers: 5
  random_seed: 0

celltypist:
  model: Immune_All_Low.pkl
  mode: best_match
  p_thres: 0.5
  use_gpu: false

marker_review:
  marker_file: /abs/path/to/markers.yaml
```

## Marker file format

The optional marker file must be YAML. Two simple formats are accepted:

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
B_cells:
  markers:
    - MS4A1
    - CD79A
```

## Runtime behavior

`./run.sh` does the following:

1. seeds `config/annotation_config.yaml` from the commented template if needed
2. reads YAML settings and environment overrides
3. writes `config/annotation_config.resolved.yaml`
4. writes the internal `config/project.toml`
5. records `results/run_info.yaml`
6. installs the Pixi environment if needed
7. runs `build_annotation_outputs.py` once
8. renders `annotation_overview.qmd`
9. renders one sub-report for each selected method
10. writes `results/software_versions.json`

The analysis itself:

- loads the input AnnData object
- checks the requested cluster column
- requires `X_umap` for review plots
- prepares a CellTypist-compatible expression view
- runs CellTypist prediction
- computes per-cell confidence
- summarizes predictions per cluster
- optionally scores marker sets for review
- writes conservative final labels that keep uncertain clusters as `Unknown`

## Outputs

- `results/adata.annotated.h5ad`
- `results/tables/cell_annotation_predictions.csv`
- `results/tables/cluster_annotation_summary.csv`
- `results/tables/marker_review_summary.csv`
- `results/tables/annotation_status_summary.csv`
- `results/tables/method_comparison.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/annotation_overview.html`
- `reports/celltypist.html`

## Annotation methods and template fit

This template is designed around a multi-report comparison structure, but only
Python-native backends are considered in-scope.

| Tool | Runtime | Best use | Template role | Current status | Caveat | References |
| --- | --- | --- | --- | --- | --- | --- |
| CellTypist | Python | Routine reference-based cell type annotation | Primary production backend | Implemented | Strongly depends on reference/model relevance | [Docs](https://celltypist.readthedocs.io/), [Paper](https://pubmed.ncbi.nlm.nih.gov/35549406/) |
| scANVI | Python | Reference mapping with batch-aware semi-supervised modeling | Future annotation backend | Planned | Heavier setup and raw-count assumptions must be enforced | [Docs](https://scvi-tools.readthedocs.io/en/latest/user_guide/models/scanvi.html), [Framework](https://docs.scvi-tools.org/en/latest/index.html) |
| decoupler | Python | Marker/pathway activity review | Future review layer, not standalone final annotation | Planned | Better for validation than for single-label assignment | [Docs](https://decoupler.readthedocs.io/en/stable/notebooks/scell/rna_sc.html), [Paper](https://academic.oup.com/bioinformaticsadvances/article/2/1/vbac016/6544613) |
| scDeepSort | Python | Pretrained human/mouse annotation in supported settings | Possible experimental backend | Not implemented | Older Python/runtime constraints make maintenance harder | [Docs](https://scdeepsort.readthedocs.io/en/master/installation.html), [Paper](https://academic.oup.com/nar/article/49/21/e122/6368052) |
| scGPT | Python | Research-oriented foundation-model annotation and mapping | Possible experimental backend | Not implemented | High compute and operational complexity | [Docs](https://scgpt.readthedocs.io/), [Paper](https://www.nature.com/articles/s41592-024-02201-0) |

R-based tools intentionally excluded from this template:

- `scmap`
- `scPred`

If those are ever needed, they should live in a separate mixed-language template
instead of expanding this Python runtime.

## Clear usage patterns

Use this template when:

- you already completed preprocessing and clustering
- you want an editable annotation workspace rather than a black-box result
- you want HTML reports plus an updated `.h5ad`
- you want to rerun the annotation step by editing a single YAML file

Do not use this template as the only source of biological truth when:

- the CellTypist model is not a good match for your tissue, species, or assay
- the dataset is highly novel and marker-driven review will dominate
- integration has removed too much gene-level structure for classifier use

## Test command

```bash
cd templates/scverse_scrna_annotate
python3 test.py
```
