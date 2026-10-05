# export in izkf_pack

The [`export`](../templates/export/README.md) template creates a reviewable
export bundle and submits it to the export backend. Create or submit the
currently prepared export with:

```bash
linkar run export
```

If no saved job ID exists, Linkar creates an export. If saved state exists, it
updates that export while preserving its job ID, username, password, and
publisher links.

The most important public artifact is:

- `results/export_job_spec.json`

This file is the structured export plan. It records what should be copied,
where it should go, and which report links should appear in the final export
report.

Credentials are stored separately in `results/export_credentials.json` with owner-only (`0600`)
permissions. This private file is intentionally omitted from the Linkar output contract; the public
job spec, submission record, terminal messages, and final-message artifact do not retain the
password.

## How export mappings work

The export behavior is mainly data-driven through:

- [`templates/export/export_mapping.table.yaml`](../templates/export/export_mapping.table.yaml)

Each mapping entry describes:

- which template it applies to
- which source path should be exported
- where that path should land in the export tree
- which report links should be created

This is why export behavior is usually best changed in the mapping table first,
not by editing report-generation code.

## Visible path vs history path

This pack distinguishes between:

- the visible workspace path, such as `summary/` or `nfcore_bile_duct/`
- historical run snapshots under `.linkar/runs/...`

For export, the preferred behavior is to use the visible project path whenever
that is the active workspace. This keeps exported reports readable and avoids
accidentally exporting stale historical bundles.

## Clean before export

Some analysis templates create large runtime directories that should not be
part of a project export, especially Nextflow `work/` directories and template
local `.pixi/` environments.

Before preparing an export, preview the project-level cleanup plan:

```bash
linkar clean . --dry-run
```

If the plan only contains disposable runtime artifacts, apply it:

```bash
linkar clean .
```

The cleanup policy is declared by each template in `linkar_template.yaml`.
Linkar applies those template-level rules to recorded project workspaces; it
does not use a pack-wide hard-coded list. This keeps `nfcore_*`, Pixi/Python,
and demultiplex cleanup behavior separate and reviewable.

Rendered `run.sh` scripts in this pack also run template-local cleanup after
successful manual execution, immediately after `linkar collect`. Running
project-level `linkar clean .` before export is still useful for older rendered
workspaces, partially rerun projects, and any artifacts that were recreated
after the last `run.sh` finished.

## Normal updates and review

Normal runs preserve an existing `export_job_spec.json`. Rebuild it explicitly
when newly generated reports or mapping changes must appear in the export.

Practical rule:

- use `linkar run export` to create or update from the prepared specification
- use `--refresh` to rebuild the specification from current project outputs
- use `--prepare` to stop before API submission
- use `--job-id JOB_ID` only to recover local state for a known server-side job
- use `--new` only when a new identity and credentials are intentional

Recommended review flow:

```bash
linkar run export --refresh --prepare
less export/results/export_job_spec.json
linkar run export
```

`--new` does not remove an existing export. If the saved export is still active,
the command stops before changing local credentials. The export service permits
only one active export per project, so this option is an operator-level escape
hatch rather than part of the normal workflow.

## analysis summary in export

The export template can include generated analysis summary outputs and analysis summary context in
the job spec. That is useful for report traceability, but the analysis summary files
should come from the visible `summary/` workspace rather than stale
`.linkar/runs/...` history.

## Common maintenance tasks

- adjust pack export policy in `export_mapping.table.yaml`
- regenerate `export_job_spec.json` after mapping changes
- verify that report links point to visible project paths
- keep processed-data exports and report exports clearly separated

## Related docs

- [summary.md](summary.md)
- [project_history_and_archive.md](project_history_and_archive.md)
- [template_outputs.md](template_outputs.md)
