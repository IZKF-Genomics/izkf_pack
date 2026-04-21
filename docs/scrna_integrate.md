# scrna_integrate workspace notes

The [`scrna_integrate`](../templates/scrna_integrate/README.md)
template creates an editable Scanpy-based workspace for integrating multiple
single-cell RNA-seq datasets after preprocessing.

This document highlights the pack-specific assumptions that matter most for
reproducible integration runs.

## Expected input stage

The template is designed to consume the prepared AnnData output from
[`scrna_prep`](../templates/scrna_prep/README.md), not a raw
matrix export from primary processing.

With the default pack binding:

- `input_h5ad` resolves from `scrna_prep.scrna_prep_h5ad`
- `input_source_template` resolves from the latest `scrna_prep` run

## Batch metadata are required

Integration only makes sense when the chosen batch variable represents at least
two real groups.

Current pack behavior:

- the configured `batch_key` must exist in `adata.obs`
- the column must contain at least two non-empty categories
- the run fails instead of fabricating placeholder batch labels

## Raw-count requirement for scVI and scANVI

For `integration_method=scvi` or `integration_method=scanvi`, the template
requires raw counts in `adata.layers["counts"]`.

This is enforced as a hard validation step because the latent model should not
be trained on already normalized expression values.

## Baseline-first evaluation

The workspace always computes and reports an unintegrated baseline before
correction. This is intentional.

The baseline view helps answer:

- whether integration is needed at all
- whether the apparent batch effect is global or cluster-specific
- whether the corrected result looks plausibly improved or overcorrected

## Quantitative diagnostics

The report includes more than embedding plots alone.

Native diagnostics currently include:

- neighborhood batch-entropy summaries
- same-batch neighbor fractions
- label silhouette scores when labels are available
- graph connectivity when labels are available

Optional `scIB` metrics are attempted only when:

- `run_scib_metrics` is enabled
- the package is installed in the runtime environment
- the required label metadata are present

## Output expectations

Important outputs include:

- `results/adata.integrated.h5ad`
- `results/tables/integration_summary.csv`
- `results/tables/integration_metrics.csv`
- `results/tables/batch_mixing_summary.csv`
- `results/tables/cluster_counts.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/qc.html`

## Maintenance notes

When editing this template, treat these as high-sensitivity areas:

- batch-key validation
- counts-layer enforcement for scVI and scANVI
- sparse-safe PCA and classical integration paths
- metric definitions and interpretation text
- output paths consumed by export and methods generation

## Related docs

- [scrna_prep.md](scrna_prep.md)
- [template_outputs.md](template_outputs.md)
- [software_versions.md](software_versions.md)
