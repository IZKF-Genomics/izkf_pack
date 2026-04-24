# Tier 1: Quick Preview

Tier 1 is the new default entry point for `scrna_annotate`.

Its job is to answer one question quickly:

- What does a first-pass annotation landscape look like if we optimize for low setup burden rather than maximum precision?

This tier should work with only:

- `global.input_h5ad`
- `global.cluster_key`

Current scaffold behavior:

- validates the input object
- records the workflow context
- writes a preview AnnData object with conservative placeholder labels
- writes a cluster-level preview summary
- writes a cluster top-marker table for the next tier
- renders a simple HTML summary pointing the user to Tier 2 next

Planned method integrations:

- `CellAnnotator`
- optional `GPTCelltype`
- `manual_review` fallback

Outputs:

- `results/adata.preview.h5ad`
- `results/tables/preview_consensus.csv`
- `results/tables/preview_disagreement_summary.csv`
- `results/tables/cluster_top_markers.csv`
- `reports/01_quick_preview.html`
