# izkf_pack Docs

This folder is for pack-specific documentation that is broader than a single
template README and more stable than issue threads or commit history.

Template-local usage should stay in `templates/*/README.md`. This `docs/`
folder is a better place for cross-cutting conventions, design decisions, and
maintenance notes that apply across multiple templates.

## Current docs

- [software_versions.md](software_versions.md): how template-level
  `software_versions_spec.yaml` files relate to generated
  `results/software_versions.json` outputs.

## Recommended next docs

- `methods.md`
  Explain how the `methods` template builds long/short drafts, where citations
  come from, when LLM polishing is used, and how deterministic fallbacks work.

- `export.md`
  Document export mapping philosophy, visible-path vs history-path behavior, and
  how `export_job_spec.json` is rebuilt or reused.

- `nfcore_templates.md`
  Capture the common `run.py -> generated run.sh` pattern, command recording,
  relative paths in rendered launchers, and template conventions shared by
  `nfcore_3mrnaseq` and `nfcore_methylseq`.

- `project_history_and_archive.md`
  Describe how pack templates interact with Linkar project history, visible
  workspaces, `.linkar/runs`, archive templates, and when `linkar project prune`
  should be used.

- `template_outputs.md`
  Define output naming conventions such as `run_info.yaml`,
  `software_versions.json`, `runtime_command.json`, HTML reports, and how these
  outputs are consumed later by `methods` and `export`.

- `facility_defaults.md`
  Record facility-specific assumptions such as common UMI labels, spike-in
  shorthands, archive destinations, and metadata conventions that appear across
  templates.

- `scverse_scrna_prep.md`
  Explain accepted input types, raw-count expectations for `.h5ad`, sample
  metadata behavior, and QC/clustering assumptions for the scRNA workspace.

## Authoring guidance

- Prefer docs that explain pack behavior across multiple templates or commands.
- Prefer relative links so the docs read well on GitHub.
- When a design is enforced in code, point to the relevant file instead of
  duplicating large code snippets.
- Keep template READMEs task-oriented and keep this folder design-oriented.
