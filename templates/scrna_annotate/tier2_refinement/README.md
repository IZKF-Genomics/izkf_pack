# Tier 2: Refinement

Tier 2 consumes Tier 1 outputs and turns a coarse preview into a more
interpretable review layer.

Its job is to answer:

- Which preview labels look biologically plausible?
- Which clusters still need review?
- Is the dataset ready for formal annotation, or should the user stay in a
  conservative review workflow?

Current scaffold behavior:

- checks for Tier 1 outputs
- writes a refinement summary table
- reads Tier 1 top markers
- scores user-supplied marker sets when a marker file is provided
- renders a lightweight HTML report

Planned refinement features:

- marker review
- cluster top markers
- broad lineage collapsing
- disagreement triage
