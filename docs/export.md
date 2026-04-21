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

## Rebuild vs reuse

The export template can reuse an existing `export_job_spec.json` if one is
already present. This is useful when the user wants to review the prepared spec
without rebuilding it every time, but it can also cause confusion if mappings
changed since the spec was first built.

Practical rule:

- if the mapping table or project outputs changed, rebuild the spec
- if the user is only reviewing the same planned export, reuse is fine

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
