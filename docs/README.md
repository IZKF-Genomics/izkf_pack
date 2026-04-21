# izkf_pack Docs

This folder is for pack-specific documentation that is broader than a single
template README and more stable than issue threads or commit history.

The root [README.md](../README.md) should stay the main navigation page and
quick-start guide for the repository. This `docs/` folder is the deeper layer
for pack-wide behavior, conventions, and design notes.

Template-local usage should stay in `templates/*/README.md`. This `docs/`
folder is a better place for cross-cutting conventions, design decisions, and
maintenance notes that apply across multiple templates.

## Current docs

- [software_versions.md](software_versions.md): how template-level
  `software_versions_spec.yaml` files relate to generated
  `results/software_versions.json` outputs.
- [methods.md](methods.md): how publication-oriented methods drafts are built,
  refined, and exported.
- [export.md](export.md): how export mappings, visible paths, and
  `export_job_spec.json` behave.
- [nfcore_templates.md](nfcore_templates.md): common conventions shared by
  `nfcore_3mrnaseq` and `nfcore_methylseq`.
- [project_history_and_archive.md](project_history_and_archive.md): how pack
  templates interact with Linkar project history, visible workspaces, and
  archive workflows.
- [template_outputs.md](template_outputs.md): common runtime artifact names and
  how downstream templates use them.
- [facility_defaults.md](facility_defaults.md): facility-specific assumptions
  used across templates.
- [scverse_scrna_prep.md](scverse_scrna_prep.md): input expectations,
  raw-count behavior, and QC assumptions for the scRNA preprocessing workspace.
- [scverse_scrna_integrate.md](scverse_scrna_integrate.md): integration
  assumptions, batch-key validation, and evaluation expectations for the scRNA
  integration workspace.

## Authoring guidance

- Prefer docs that explain pack behavior across multiple templates or commands.
- Prefer relative links so the docs read well on GitHub.
- When a design is enforced in code, point to the relevant file instead of
  duplicating large code snippets.
- Keep template READMEs task-oriented and keep this folder design-oriented.
