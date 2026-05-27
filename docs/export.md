# export in izkf_pack

The [`export`](../templates/export/README.md) template prepares a reviewable
export bundle and, when requested, submits it to the export backend.

The most important artifact is:

- `results/export_job_spec.json`

This file is the structured export plan. It records what should be copied,
where it should go, and which report links should appear in the final export
report.

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

- the visible workspace path, such as `methods/` or `nfcore_bile_duct/`
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

## Rebuild vs reuse

The export template can reuse an existing `export_job_spec.json` if one is
already present. This is useful when the user wants to review the prepared spec
without rebuilding it every time, but it can also cause confusion if mappings
changed since the spec was first built.

Practical rule:

- `bash run.sh` now rebuilds the spec, generates new credentials, and submits
- use `--reuse-spec` when a manually edited or already-approved spec should be
  submitted unchanged
- use `--reuse-credentials` when the spec should be rebuilt but the client
  credentials should stay stable
- use `--prepare-only` when you want to inspect the prepared bundle before
  submission

Recommended update flow when only report links changed and the client
credentials should stay fixed:

```bash
cd export
bash run.sh --reuse-credentials --prepare-only
less results/export_job_spec.json
```

With credential reuse enabled, the export template looks for a complete
username/password pair in `export_submission.json` first, then
`export_job_spec.json`, then export params recorded in `project.yaml`.

Recommended review flow:

```bash
linkar render export --outdir ./export
cd export
less results/export_job_spec.json
bash run.sh
```

## methods in export

The export template can include generated methods outputs and methods context in
the job spec. That is useful for report traceability, but the methods files
should come from the visible `methods/` workspace rather than stale
`.linkar/runs/...` history.

## Common maintenance tasks

- adjust pack export policy in `export_mapping.table.yaml`
- regenerate `export_job_spec.json` after mapping changes
- verify that report links point to visible project paths
- keep processed-data exports and report exports clearly separated

## Related docs

- [methods.md](methods.md)
- [project_history_and_archive.md](project_history_and_archive.md)
- [template_outputs.md](template_outputs.md)
