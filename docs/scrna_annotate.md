# scrna_annotate workspace notes

The [`scrna_annotate`](../templates/scrna_annotate/README.md) template is a
tiered Scanpy-based annotation workflow.

The rebuilt structure is intentionally progressive:

- Tier 1: quick preview
- Tier 2: refinement
- Tier 3: formal annotation

This document records the pack-specific assumptions behind the current
implementation.

## Workflow model

The old single-directory annotation runtime is being replaced by a workflow that
separates annotation into three user-facing layers:

- `tier1_quick_preview`
- `tier2_refinement`
- `tier3_formal_annotation`

The top-level template directory now acts as a workflow orchestrator rather than
as a single monolithic runtime.

Current top-level entrypoint:

- `templates/scrna_annotate/run.sh`

Top-level workflow config:

- `templates/scrna_annotate/config/workflow.yaml`

## Why the template uses tiers

The rebuild is driven by three practical issues in the older design:

- users had to think about formal annotation too early
- `CellTypist` was the only real backend, but many datasets do not have a
  suitable model
- review, preview, and formal annotation concerns were mixed into one runtime

The rebuilt design follows single-cell best practices more closely:

- let users see something first
- keep uncertainty visible
- only enable reference-aware annotation when the reference really fits

## Current tier status

### Tier 1

Current behavior:

- validates the input AnnData object
- requires a cluster column and `X_umap`
- writes conservative preview labels
- writes cluster-level preview summaries
- writes cluster top-marker tables
- renders a quick preview report

Current outputs include:

- `tier1_quick_preview/results/adata.preview.h5ad`
- `tier1_quick_preview/results/tables/preview_consensus.csv`
- `tier1_quick_preview/results/tables/preview_disagreement_summary.csv`
- `tier1_quick_preview/results/tables/cluster_top_markers.csv`
- `tier1_quick_preview/reports/01_quick_preview.html`

Tier 1 is meant to be low-setup and safe by default. It is the default
execution path of the workflow.

### Tier 2

Current behavior:

- consumes Tier 1 outputs
- writes conservative refinement suggestions
- reads Tier 1 cluster top markers
- optionally scores user-supplied marker sets
- renders a refinement report

Current outputs include:

- `tier2_refinement/results/adata.refined.h5ad`
- `tier2_refinement/results/tables/refinement_suggestions.csv`
- `tier2_refinement/results/tables/marker_review_summary.csv`
- `tier2_refinement/results/tables/cluster_marker_candidates.csv`
- `tier2_refinement/reports/02_refinement.html`

Tier 2 is not intended to replace formal reference-based annotation. Its role
is to strengthen or challenge Tier 1 preview labels before the user commits to
a formal method.

### Tier 3

Current behavior:

- consumes Tier 2 outputs
- reads Tier 3 formal annotation config
- runs `CellTypist` when enabled and configured
- writes formal prediction tables
- writes an annotated H5AD
- renders a formal annotation report

Current outputs include:

- `tier3_formal_annotation/results/adata.annotated.h5ad`
- `tier3_formal_annotation/results/tables/formal_annotation_predictions.csv`
- `tier3_formal_annotation/results/tables/formal_annotation_summary.csv`
- `tier3_formal_annotation/reports/03_formal_annotation.html`

Tier 3 is intentionally not the default execution path.

## Current method scope

The rebuilt template remains intentionally Python-only.

Currently active or scaffolded methods:

- Tier 1 quick preview scaffold
- Tier 2 marker-backed refinement scaffold
- Tier 3 `CellTypist`

Still planned for later integration:

- `scANVI`
- `decoupler` as a richer review layer
- selected low-setup quick-preview tools when operationally justified

Still intentionally out of scope:

- `scmap`
- `scPred`

Those remain excluded because they would pull the template back into a
mixed-language runtime before the Python-first rebuild is stable.

## Default input preference

The rebuilt workflow still assumes that the most natural upstream source is the
latest `scrna_prep` output.

Reason:

- preview and formal annotation both benefit from the broader feature space in a
  prep-stage object

Using an integration-stage object is still possible, but should remain an
intentional user choice rather than a silent default.

## CellTypist assumptions still matter

Although the workflow has been redesigned, the `CellTypist` backend still has
the same biological and technical constraints:

- a relevant reference model is critical
- the method expects usable gene symbols
- the expression view should be compatible with log-normalized prediction

The workflow changes user experience and structure, but it does not make an
ill-matched reference safer.

## Output philosophy

The rebuild continues to enforce a conservative output policy:

- preview labels are not final labels
- refinement labels are not final labels
- formal labels should still be reviewable
- unresolved clusters should remain `Unknown`

This is a deliberate design choice and should not be relaxed just because the
workflow is now easier to run.

## Maintenance notes

When editing the rebuilt template, treat these as high-sensitivity areas:

- tier-to-tier input and output contracts
- shared helper modules in `shared/lib/`
- top-level workflow orchestration in `run.sh`
- preview marker ranking assumptions
- formal annotation label naming and final-label write logic

## Related docs

- [scrna_annotate_redesign.md](scrna_annotate_redesign.md)
- [scrna_annotate_rebuild_plan.md](scrna_annotate_rebuild_plan.md)
- [scrna_prep.md](scrna_prep.md)
- [scrna_integrate.md](scrna_integrate.md)
- [template_outputs.md](template_outputs.md)
