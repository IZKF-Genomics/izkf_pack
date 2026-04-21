# scverse_scrna_annotate workspace notes

The [`scverse_scrna_annotate`](../templates/scverse_scrna_annotate/README.md)
template creates an editable Scanpy-based workspace for cell type annotation
review after preprocessing or integration.

This document records the pack-specific assumptions behind the first
implementation.

## Config model

The user-facing entrypoint is now a commented YAML file:

- `templates/scverse_scrna_annotate/config/00_annotation_config.yaml`

If it is missing, `run.sh` seeds it from:

- `templates/scverse_scrna_annotate/assets/00_annotation_config.template.yaml`

The runtime then converts that YAML config into the internal
`config/project.toml` file consumed by the builder and report code.

Environment variables still override YAML values when both are present.

## Python-only scope

This template is intentionally Python-only. Current and planned in-scope
backends are:

- `CellTypist`
- future `scANVI`
- future `decoupler` review
- future `scGPT`

R-centered tools such as `scmap` and `scPred` are intentionally excluded from
this workspace to keep the runtime simpler and more maintainable.

## Default input preference

Although the template can read either a prep-stage or integrate-stage AnnData
object, the default pack binding prefers the latest
[`scverse_scrna_prep`](../templates/scverse_scrna_prep/README.md) output.

This is intentional for v0.1 because the CellTypist workflow benefits from a
broader feature space than an HVG-only integration object may provide.

Current behavior:

- prefer `scverse_scrna_prep.scrna_prep_h5ad`
- fall back to `scverse_scrna_integrate.integrated_h5ad` only when no prep
  output is available

## Automated labels are not treated as final truth

The annotation template keeps three layers distinct:

- per-cell predicted labels
- cluster-level suggested labels
- final labels after review rules

Clusters that do not meet the configured dominance and confidence thresholds are
left unresolved as `Unknown` rather than being silently assigned a label.

## CellTypist input expectation

CellTypist expects gene symbols and a log1p-normalized expression matrix. The
template therefore:

- resolves gene symbols from known `adata.var` columns when feature IDs are used
- prepares a log-normalized expression view for prediction when the current
  matrix does not already look like log1p-normalized data

If the input lacks a usable gene-symbol representation, the run stops with a
clear error.

## Marker review

Marker sets are optional in v0.1. When supplied, they are used as a review
layer rather than as a silent override of the classifier output.

This means marker-based summaries can downgrade confidence in a cluster label,
but they do not automatically replace the underlying classifier prediction
without explicit user review.

## Output expectations

Important outputs include:

- `results/adata.annotated.h5ad`
- `results/tables/cell_annotation_predictions.csv`
- `results/tables/cluster_annotation_summary.csv`
- `results/tables/marker_review_summary.csv`
- `results/tables/annotation_status_summary.csv`
- `results/tables/method_comparison.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/00_annotation_overview.html`
- `reports/01_celltypist.html`
- `reports/02_scanvi.html`
- `reports/03_decoupler_review.html`
- `reports/04_scdeepsort.html`
- `reports/05_scgpt.html`

Important config files include:

- `config/00_annotation_config.yaml`
- `config/00_annotation_config.resolved.yaml`
- `config/project.toml`

Method-specific report scaffolds currently present in the template directory:

- `01_celltypist.qmd`
- `02_scanvi.qmd`
- `03_decoupler_review.qmd`
- `04_scdeepsort.qmd`
- `05_scgpt.qmd`

At the moment only `01_celltypist.qmd` is backed by executable runtime logic.
The later numbered QMD files are rendered scaffold reports so future
Python-native backends can slot into the same report organization without
another directory refactor.

## Maintenance notes

When editing this template, treat these as high-sensitivity areas:

- default input selection between prep and integrate outputs
- gene symbol resolution
- CellTypist preprocessing assumptions
- cluster-level acceptance logic
- output paths consumed by export and methods generation

## Related docs

- [scverse_scrna_prep.md](scverse_scrna_prep.md)
- [scverse_scrna_integrate.md](scverse_scrna_integrate.md)
- [template_outputs.md](template_outputs.md)
