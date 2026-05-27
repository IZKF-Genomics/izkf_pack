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

## Runtime cleanup

Templates declare disposable runtime artifacts in `linkar_template.yaml` under
`cleanup`. Linkar can apply these rules from either a rendered template
directory or the project root:

```bash
linkar clean . --dry-run
linkar clean . --yes
```

Cleanup rules should stay template-specific. For example, nf-core templates
declare Nextflow `work/`, `.nextflow/`, and `.nextflow.log*`, while Pixi/Python
templates declare `.pixi/` and `__pycache__/`. Scientific outputs, reports, and
declared Linkar outputs should not be listed as cleanup targets.

Current policy:

| Template group | Cleanup targets |
| --- | --- |
| nf-core / Nextflow templates | `.pixi/`, `work/`, `.nextflow/`, `.nextflow.log*` |
| Pixi/Python report and analysis templates | `.pixi/`, `__pycache__/` |
| `demultiplex` | `.pixi/`, `demultiplexing_prefect/` |

Template authors should add cleanup metadata when a new template creates large
or reproducible runtime state outside `results/`.

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
