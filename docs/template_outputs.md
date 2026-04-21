# common template outputs

Many templates in `izkf_pack` write a similar set of runtime artifacts. These
files are important because other templates, especially `methods` and `export`,
consume them later.

## Common output files

### `run_info.yaml`

Purpose:

- record resolved parameters
- record key runtime context
- give users a readable summary of how the workspace was configured

Common use:

- helpful for template-local inspection
- useful when a template has many resolved defaults

### `software_versions.json`

Purpose:

- record tool versions and important static or parameter-backed version labels

Common use:

- methods generation
- provenance tracking
- export traceability

See also [software_versions.md](software_versions.md).

### `runtime_command.json`

Purpose:

- preserve the effective command and resolved runtime context in a structured way

Common use:

- methods generation
- debugging
- confirming whether optional workflow behavior was really enabled

This is especially important for templates where the visible `run.sh` is
generated dynamically.

### HTML reports

Examples:

- Quarto HTML outputs
- methods HTML companions

Purpose:

- human-readable review artifacts
- export-ready reports

### `.h5ad`, tables, and JSON summaries

These are template-specific scientific outputs, but they often follow a common
pattern:

- primary data object, for example `adata.prep.h5ad`
- summary tables under `results/tables/`
- small JSON summaries for machine-readable reporting

## Why naming consistency matters

This pack benefits from stable output names because:

- `methods` can discover artifacts more reliably
- `export` mappings stay simpler
- users learn the pattern once and can inspect many templates the same way

## Good maintenance rules

- keep the artifact names stable when possible
- when renaming an artifact, check `methods`, `export`, and tests
- prefer structured JSON/YAML for provenance and Markdown/HTML for user-facing summaries

## Related docs

- [software_versions.md](software_versions.md)
- [methods.md](methods.md)
- [export.md](export.md)
