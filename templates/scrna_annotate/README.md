# `scrna_annotate`

`scrna_annotate` is a tiered single-cell annotation workflow built around a
progressive user experience.

The new design is intentionally progressive:

- Tier 1: quick preview with the lowest setup burden
- Tier 2: refinement and marker-backed review
- Tier 3: formal reference-aware annotation

The main user experience goal is simple:

- let the user see a result first
- then decide whether refinement is needed
- only ask for formal models and reference choices later

This follows the single-cell best-practices view that annotation should be
treated as a staged review process rather than a one-click source of truth.

Reference:
- Single-cell best practices, annotation chapter:
  <https://www.sc-best-practices.org/cellular_structure/annotation.html>

## New Layout

```text
scrna_annotate/
  README.md
  run.sh
  config/
    workflow.yaml
  tier1_quick_preview/
  tier2_refinement/
  tier3_formal_annotation/
  shared/
```

Each tier owns its own:

- `run.sh`
- `run.py`
- `config/`
- `results/`
- `reports/`

The top-level `run.sh` acts as a workflow orchestrator.

## Quick Start

1. Open [config/workflow.yaml](config/workflow.yaml)
2. Fill in:
   - `global.input_h5ad`
   - `global.cluster_key` if your input does not use `leiden`
3. Run:

```bash
./run.sh
```

Default behavior:

- runs Tier 1 only
- writes Tier 1 outputs to `tier1_quick_preview/results/`
- renders the first report to `tier1_quick_preview/reports/01_quick_preview.html`
- updates the workflow overview at `reports/00_overview.html`

## Workflow Commands

Run the default entry tier:

```bash
./run.sh
```

Run one specific tier:

```bash
./run.sh --tier tier1
./run.sh --tier tier2
./run.sh --tier tier3
```

Run a range:

```bash
./run.sh --from tier1 --to tier3
```

## Tier Summary

## Tier 1: Quick Preview

Purpose:

- give the user a first-pass annotation landscape with minimal setup

Current outputs:

- `results/adata.preview.h5ad`
- `results/tables/preview_consensus.csv`
- `results/tables/preview_disagreement_summary.csv`
- `reports/01_quick_preview.html`

Current behavior:

- validates the input
- checks that `cluster_key` and `X_umap` exist
- writes conservative placeholder preview labels
- points the user toward Tier 2 refinement

Current quick-preview default:

- conservative preview labels
- cluster-level disagreement summary
- cluster top markers for the next tier
- marker-ready handoff into Tier 2

## Tier 2: Refinement

Purpose:

- review preview outputs
- add marker-backed evidence
- decide whether broad lineage labels are already defensible

Current outputs:

- `results/adata.refined.h5ad`
- `results/tables/refinement_suggestions.csv`
- `results/tables/marker_review_summary.csv`
- `results/tables/cluster_marker_candidates.csv`
- `reports/02_refinement.html`

Current refinement behavior:

- reads Tier 1 outputs
- carries cluster top markers into refinement summaries
- scores marker sets when a marker file is provided
- writes a refinement-ready AnnData object for Tier 3

## Tier 3: Formal Annotation

Purpose:

- run formal reference-aware methods only after the user is ready

Current outputs:

- `results/run_info.yaml`
- `results/adata.annotated.h5ad` when enabled
- `results/tables/formal_annotation_predictions.csv` when enabled
- `results/tables/formal_annotation_summary.csv` when enabled
- `reports/03_formal_annotation.html`

Current formal backend:

- `CellTypist`

Planned later backend:

- `scANVI`

## Config Model

The workflow starts from one top-level workflow config:

- [config/workflow.yaml](config/workflow.yaml)

Tier-specific configs live in:

- [tier1_quick_preview/config/00_quick_preview_config.yaml](tier1_quick_preview/config/00_quick_preview_config.yaml)
- [tier2_refinement/config/00_refinement_config.yaml](tier2_refinement/config/00_refinement_config.yaml)
- [tier3_formal_annotation/config/00_formal_annotation_config.yaml](tier3_formal_annotation/config/00_formal_annotation_config.yaml)

This keeps first-run setup small while still letting later tiers expose
specialized parameters.

## Why This Template Uses Tiers

The workflow is organized to keep the first user decision small and safe.

The rebuilt design separates responsibilities:

- Tier 1 should be easy to run
- Tier 2 should help the user understand uncertainty
- Tier 3 should only be used when a suitable formal method exists

That means the workflow is organized around decisions, not around tool names.

## Recommended Use Right Now

Use this template when:

- you want to exercise the new tier structure
- you want a conservative quick preview entrypoint
- you want a clear preview -> refinement -> formal annotation progression

Keep in mind:

- Tier 1 favors safety and speed over confident final labels
- Tier 2 is designed to strengthen or challenge the Tier 1 preview
- Tier 3 should only be enabled when a suitable formal reference exists

## Test command

```bash
cd templates/scrna_annotate
python3 test.py
```
