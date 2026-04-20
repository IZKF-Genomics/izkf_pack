---
name: izkf-pack
description: Use when working in the izkf_pack repository to inspect, render, run, collect, test, or modify Linkar genomics templates and their downstream methods/export behavior. Covers pack structure, common template workflows, runtime/output conventions, and repo-specific gotchas.
---

# izkf_pack

This skill is for agent work inside the `izkf_pack` repository.

Use it when the task involves:

- editing or reviewing templates in `templates/`
- updating binding logic in `linkar_pack.yaml` or `functions/`
- helping a user render, run, collect, or inspect Linkar template outputs
- debugging project history, `.linkar/runs`, `project.yaml`, or exported reports
- improving `methods`, `export`, or `nfcore_*` template behavior

Do not load the whole repository into context. Read only the files needed for the current task.

## Repository Map

- `templates/<template_id>/`
  Template contract, runtime files, tests, and template-local docs.
- `functions/`
  Binding functions used by `linkar_pack.yaml`.
- `linkar_pack.yaml`
  Default parameter bindings for selected templates.
- `README.md`
  Human-facing pack usage.
- `TEMPLATE_AUTHORING_FOR_AGENTS.md`
  Template authoring checklist and conventions. Read this before adding or restructuring templates.

## Core Linkar Workflow

Default user workflow:

1. `linkar render <template>` to inspect or edit the rendered bundle.
2. `bash run.sh` inside the rendered directory when the template is render-first.
3. `linkar collect <outdir>` to record outputs.
4. `linkar run <template>` for one-shot execution when inspection is not needed.

Inside an active Linkar project:

- `project.yaml` records template history.
- `.linkar/runs/` stores per-run snapshots and runtime context.
- repeated renders or runs can append history even when the visible outdir stays the same.

## Important Repo Conventions

- Always prefix shell commands with `rtk`.
- Use `rg` for searching.
- Use `apply_patch` for file edits.
- Do not overwrite unrelated user edits.
- Commit each logical fix separately when making repo changes.
- Keep README paths GitHub-friendly; do not write workstation-specific paths in docs.

## Template Design Rules

Follow `TEMPLATE_AUTHORING_FOR_AGENTS.md` for new templates and major refactors.

Important local conventions:

- Prefer `run.py` once logic becomes nontrivial.
- Keep `run.sh` thin and human-friendly.
- For command-wrapper templates, prefer:
  `run.py` resolves parameters -> writes exact editable `run.sh` -> executes it.
- Record stable outputs in `linkar_template.yaml` so downstream templates can reuse them.
- Add or update `test.py` whenever runtime behavior changes.

## High-Value Templates

### `demultiplex`

- Starts from raw sequencing run folders.
- Produces FASTQ, QC, and MultiQC outputs.
- Often seeds downstream project adoption.

### `nfcore_3mrnaseq`

- Wraps `nf-core/rnaseq` for facility 3' mRNA-seq usage.
- Current repo preference:
  rendered `run.sh` should show the exact multiline Nextflow command clearly.
- `umi` and `spikein` support facility shorthands like `true`, but methods text should reflect the actual rendered command.
- Prefer relative paths in rendered commands where possible.

### `nfcore_methylseq`

- Similar class of template to `nfcore_3mrnaseq`.
- Good candidate for the same `run.py -> generated run.sh` pattern.

### `dgea`

- Editable downstream analysis workspace.
- Uses quantified RNA-seq outputs and generates HTML reports.
- GO / GSEA references should match the actual package used by the template.

### `ercc`

- Spike-in QC report template.
- Exported reports should focus on user-facing QC outputs, not low-value runtime metadata links unless explicitly wanted.

### `methods`

- Generates `methods_long.md`, `methods_short.md`, citations, and prompt/response artifacts.
- LLM polishing is enabled by default.
- Publication-facing wording matters more than internal template trivia.
- For nf-core sections, UMI, genome, spike-in, and key parameters should come from the rendered or recorded command when available, not only from Agendo metadata.
- `methods_short.md` should be a clean condensation of the long version, not an unrelated summary.

### `export`

- Builds `export_job_spec.json` and submits export jobs.
- If `export_job_spec.json` already exists, current logic can reuse it instead of rebuilding.
- When export output looks stale, inspect the existing spec before changing mappings.
- `report_links` in the spec come from `templates/export/export_mapping.table.yaml`.

## Project History And `.linkar/runs`

Understand the distinction:

- visible rendered bundle: the current working directory such as `methods/` or `nfcore_bile_duct/`
- history snapshot: `.linkar/runs/<instance_id>/`
- project registry: `project.yaml`

Useful implications:

- one visible outdir does not imply one history entry
- `--refresh` rerenders the visible bundle before execution; it does not mean “collapse history”
- templates may rely on `history_path` when reconstructing prior runs

Do not casually delete `.linkar/runs` or old `project.yaml` entries unless the user explicitly wants to drop provenance.

## Methods And Publication Style

When editing methods generation:

- prefer publication-ready scientific prose
- remove authoring chatter, internal implementation notes, and facility-internal wording unless scientifically relevant
- use lists for grouped settings instead of dense parameter sentences
- include references and citations only when they correspond to real tools or methods in use
- keep `methods_long.md` detailed but tidy
- keep `methods_short.md` readable in manuscript style, ideally with inline numbered citations

If the user asks for journal style, align with the requested journal's conventions, but stay grounded in recorded project provenance.

## Export Debugging Checklist

When exported reports do not match the latest mapping:

1. inspect `templates/export/export_mapping.table.yaml`
2. inspect `export/results/export_job_spec.json`
3. confirm whether the builder reused an existing spec
4. regenerate the spec before assuming the mapping change failed

When the export summary looks noisy:

- prefer counted template summaries over raw repeated ids
- remember that export entries come from the mapping/spec, not directly from the number of project history entries

## Useful Files To Inspect

Depending on the task, start with:

- `project.yaml`
- `.linkar/meta.json`
- `.linkar/runtime.json`
- `results/runtime_command.json`
- `results/software_versions.json`
- template `test.py`
- template `README.md`

For methods/export work, also inspect:

- `templates/methods/methods_catalog.yaml`
- `templates/export/export_mapping.table.yaml`

## Validation

After template changes, run the smallest relevant verification:

- template-local `test.py`
- targeted render/run dry-run checks when safe
- YAML validation for `linkar_template.yaml` edits

If a change affects docs and runtime behavior, update both.

## Output Style For Agents

When helping users with `izkf_pack`:

- explain whether behavior comes from the visible rendered bundle, the recorded runtime command, or project history
- distinguish current files from stale cached/exported artifacts
- prefer concrete file references over abstract descriptions
- avoid guessing how Linkar core behaves when local evidence is missing; inspect help text or generated files first
