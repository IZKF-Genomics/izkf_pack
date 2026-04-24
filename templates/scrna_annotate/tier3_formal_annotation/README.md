# Tier 3: Formal Annotation

Tier 3 is the formal, reference-aware layer of the rebuilt annotation workflow.

It should only be used after the user has reviewed Tier 1 and Tier 2 outputs
and decided that a formal method is warranted.

Current scaffold behavior:

- checks for Tier 2 outputs
- reads the Tier 3 config
- runs `CellTypist` when formal annotation is enabled and a model is configured
- writes formal prediction tables, an annotated H5AD, and a report

Current formal backend:

- `CellTypist`

Planned later backend:

- `scANVI`
