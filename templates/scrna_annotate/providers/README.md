# scrna_annotate providers

This directory contains provider manifests only. Provider execution code has not been generated yet.

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

## Planned provider order

First implementation:

1. `mock_provider`
2. `marker_based`
3. `manual_curated`
4. `celltypist`

Later:

- `singler`
- `sctype`
- `sccatch`
- `scgpt`
- `sctab`

Foundation-model providers should remain disabled by default until model and vocabulary provenance
are implemented.
