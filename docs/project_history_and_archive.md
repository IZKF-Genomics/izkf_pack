# project history and archive behavior

This pack relies on Linkar project history, but it also tries to keep the user
experience centered on visible workspaces rather than hidden run snapshots.

## Three different concepts

When working with a project, it helps to separate:

- the visible workspace
  for example `summary/` or `nfcore_bile_duct/`
- the project ledger in `project.yaml`
- historical run snapshots under `.linkar/runs/...`

These are related, but they are not the same thing.

## Visible workspaces

For interactive analysis templates in this pack, the preferred user experience
is a visible workspace that can be rerun and edited directly. Examples include:

- `summary`
- `nfcore_3mrnaseq`
- `nfcore_methylseq`
- `scrna_prep`

When possible, rerunning should overwrite the visible workspace outputs instead
of forcing users to inspect hidden historical bundles.

## Planned Linkar UX

For this pack, the preferred long-term model is:

```text
one project + one template id = one active workspace
```

That means rerendering `nfcore_3mrnaseq`, `dgea`, `scrna_prep`, or similar
stage-like templates should update the existing workspace and overwrite the
existing `project.yaml` entry by default. Extra history should be opt-in, not an
accidental side effect of rendering into a temporary directory.

The desired command behavior is:

- `linkar render TEMPLATE` refreshes `<project>/<template_id>` by default
- existing non-empty workspaces require confirmation
- `--yes` accepts confirmation for scripts
- `--fresh` recreates the workspace after confirmation
- `--new-instance` explicitly records a second instance
- external `--outdir` renders are treated as ad hoc unless explicitly adopted

Until this Linkar behavior is implemented, use `linkar project prune --dry-run`
to inspect duplicate project entries and `linkar project prune` to remove stale
history.

## Historical runs

Linkar can still record historical runs in `project.yaml` and `.linkar/runs/`.
Those records are useful for provenance, but they can become clutter if the same
visible workspace is rerendered many times.

This is why `linkar project prune` matters in current projects. It helps remove
stale historical entries and, by default, can also remove orphaned directories.

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

Use template-declared cleanup before archive/export when runtime artifacts have
grown large:

```bash
linkar clean . --dry-run
linkar clean .
```

Rendered `run.sh` scripts normally perform template-local cleanup after
successful execution, but project-level cleanup remains useful for old rendered
workspaces and artifacts recreated during manual debugging.

## Recommended user guidance

- use visible workspaces for day-to-day reruns
- use `linkar clean . --dry-run` before export or archive
- use `linkar project prune` when history becomes cluttered
- archive verified project directories with the archive templates
- avoid deleting `.linkar` blindly unless the provenance is truly no longer needed

## Related docs

- [export.md](export.md)
- [template_outputs.md](template_outputs.md)
- [facility_defaults.md](facility_defaults.md)
