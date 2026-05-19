# scrna_annotate providers

This directory contains provider manifests and provider-owned helper code.

The first implementation executes `marker_based` and optionally `marker_catalog`. Other provider
directories currently define planned manifests so the top-level runner can report them as
disabled/skipped until their execution code is added.

Each future provider should live in its own folder:

```text
providers/<provider_id>/
  provider_manifest.yaml
  README.md
  pixi.toml
  run.py or run.R
  test.py
```

The manifest is the contract between the top-level `scrna_annotate` runner and the provider. The
runner should use the manifest to plan, validate, and report readiness before execution.

Provider scripts must write:

```text
results/providers/<provider_id>/annotation_result.json
```

They should write this file for every terminal state, including `skipped`, `needs_config`, and
`failed`.

Provider scripts may also write a method-level Quarto report:

```text
results/providers/<provider_id>/report.qmd
results/providers/<provider_id>/report.html
```

The `.qmd` source is the canonical human-readable artifact. HTML rendering is optional. A provider
should still succeed when Quarto is unavailable if the annotation itself completed; record the
missing render as a warning in `annotation_result.json`.

Reports should describe provider-specific evidence and diagnostics. They are not the data contract
between `scrna_annotate` and `scrna_audit`; the audit template should read JSON and link to reports.

Provider reports should be readable before `scrna_audit` exists. Prefer:

- a short explanation of what the method did
- run context and warnings near the top
- full warning messages as readable text, not warning tables
- compact review tables instead of wide raw exports
- sortable, searchable, filterable, paginated HTML tables when dependencies are available
- interactive figures when they add value, with text fallbacks when plotting dependencies are absent
- method details and citations

For long tables, prefer review-oriented columns in the report and keep exhaustive data in provider
CSV artifacts. Do not force users to scroll through thousands of rows before seeing the evidence
summary.

Missing tissue should not block exploratory providers. If a method can still produce useful
evidence, it should run with a warning and mark the result as context-light. Tissue-specific methods
should write `needs_config` unless the required tissue, model, or reference is configured.

Provider methods can be general, but resources must be organism-aware. Marker catalogs, reference
atlases, and pretrained models should declare organism/species. Cross-species use should be refused
unless a future explicit ortholog-mapped provider records mapping provenance.

Downloaded resources should be resolved before provider execution. Providers should consume local
paths and record resource id, species, path, and checksum in `annotation_result.json`; download and
refresh policy belongs in a resource/cache layer, not inside method code.

## Planned provider order

First implementation:

1. `marker_based`
2. `marker_catalog`
3. `user_markers`
4. `mock_provider`
5. `manual_curated`
6. `celltypist`

Later:

- `singler`
- `sctype`
- `sccatch`
- `scgpt`
- `sctab`

Foundation-model providers should remain disabled by default until model and vocabulary provenance
are implemented.
