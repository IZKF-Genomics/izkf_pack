# project history and archive behavior

This pack relies on Linkar project history, but it also tries to keep the user
experience centered on visible workspaces rather than hidden run snapshots.

## Three different concepts

When working with a project, it helps to separate:

- the visible workspace
  for example `methods/` or `nfcore_bile_duct/`
- the project ledger in `project.yaml`
- historical run snapshots under `.linkar/runs/...`

These are related, but they are not the same thing.

## Visible workspaces

For interactive analysis templates in this pack, the preferred user experience
is a visible workspace that can be rerun and edited directly. Examples include:

- `methods`
- `nfcore_3mrnaseq`
- `nfcore_methylseq`
- `scverse_scrna_prep`

When possible, rerunning should overwrite the visible workspace outputs instead
of forcing users to inspect hidden historical bundles.

## Historical runs

Linkar can still record historical runs in `project.yaml` and `.linkar/runs/`.
Those records are useful for provenance, but they can become clutter if the same
visible workspace is rerendered many times.

This is why `linkar project prune` matters. It helps remove stale historical
entries and, by default, can also remove orphaned directories.

## Archive templates

This pack includes archive workflows such as:

- `archive_raw`
- `archive_fastq`
- `archive_projects`

These templates are designed for copying data to archive storage with manifest
tracking and optional cleanup after verified copy.

They are not the same as workspace cleanup.

## Cleanup philosophy

For project workspaces, transient caches such as:

- `.pixi`
- `.nextflow`
- `work`
- `.renv`

are safer cleanup targets than `.linkar` as a whole.

`.linkar` contains provenance and project history, so it should not be treated
as disposable cache by default.

## Recommended user guidance

- use visible workspaces for day-to-day reruns
- use `linkar project prune` when history becomes cluttered
- archive verified project directories with the archive templates
- avoid deleting `.linkar` blindly unless the provenance is truly no longer needed

## Related docs

- [export.md](export.md)
- [template_outputs.md](template_outputs.md)
- [facility_defaults.md](facility_defaults.md)
