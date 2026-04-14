# Linkar Template Authoring Guide For AI Agents

This document is for AI agents implementing new templates in `izkf_pack`.

It is intentionally practical. Use it as a working checklist, not as abstract design advice.

## Goal

When adding a new template, produce a result that:

- follows the current Linkar contract
- fits the style of `izkf_pack`
- is easy for humans to review and edit
- records outputs cleanly for downstream templates
- is tested before handoff
- updates both local template docs and pack-level docs

## Know The Repository Layout

Use the existing pack structure:

- `templates/<template_id>/`
  Contains the template contract, runtime files, tests, and template-local documentation.
- `functions/`
  Contains reusable binding functions referenced from `linkar_pack.yaml`.
- `linkar_pack.yaml`
  Defines default bindings for templates in this pack.
- `README.md`
  Explains pack-level usage and should mention important new templates.

For a new template, the normal minimum directory is:

```text
templates/<template_id>/
  linkar_template.yaml
  README.md
  test.py
```

Common optional files:

- `run.sh`
- `run.py`
- helper scripts or notebooks
- example static inputs such as `samplesheet.csv`
- `pixi.toml`
- `references.bib`
- `citations.yaml`

## Understand The Linkar Template Contract

New templates should use `linkar_template.yaml`.

At minimum, define:

- `id`
- `version`
- `description`
- `params`
- `outputs`
- `run`

Typical skeleton:

```yaml
id: example_template
version: 0.1.0
description: Short sentence explaining what the template does.
tools:
  required:
    - python3
params:
  input_dir:
    type: path
    required: true
    description: Input directory for the analysis.
  threads:
    type: int
    default: 4
    description: Number of CPU threads.
outputs:
  results_dir: {}
  report_html:
    path: report.html
  result_files:
    glob: output/**/*.txt
run:
  mode: direct
  entry: run.sh
```

## How To Construct `linkar_template.yaml`

### `id`

- Use a stable, lowercase, underscore-separated id.
- Match the directory name unless there is a strong reason not to.

### `version`

- Start at `0.1.0` for new templates unless there is already a migration history.
- Bump when the user-facing interface or runtime behavior changes materially.

### `description`

- Keep it short and precise.
- Describe the scientific or operational intent, not implementation trivia.

Good:

- `Generate project-level methods drafts from Linkar project history.`
- `Run Cell Ranger ATAC on a demultiplexed FASTQ directory.`

### `tools`

- Use `tools.required` for commands that must exist.
- Use `tools.required_any` when multiple equivalent commands are acceptable.
- Keep this honest. It should reflect what the template actually calls.

### `params`

Each parameter should have:

- a clear name
- a correct `type`
- `required: true` only when truly necessary
- a useful `description`

Supported types in current Linkar:

- `str`
- `int`
- `float`
- `bool`
- `path`
- `list[path]`

Best practices:

- Expose scientific knobs and true runtime choices.
- Do not expose values that should be inferred from project history or facility defaults.
- Prefer binding functions over bloated public parameter lists.
- Prefer empty-string defaults only when "unset" is a meaningful state.

### `outputs`

Declare outputs carefully. These are how downstream templates and methods generation understand prior work.

Use:

- `results_dir: {}`
  when the whole results root is meaningful
- `path: ...`
  for one important file or directory
- `glob: ...`
  for collections of files

Best practices:

- `path` and `glob` should match the template's real runtime layout. In this pack, many outputs live
  under `results/`, but that is a convention, not a hard rule.
- If an output is written under `results/`, prefer being explicit, for example
  `path: results/software_versions.json` or `glob: results/**/*.fastq.gz`, unless the template is
  already intentionally collecting from a different root.
- Declare the outputs you expect other templates to reuse.
- Prefer stable names like `multiqc_report`, `salmon_dir`, `demux_fastq_files`.
- Do not rely on undocumented files if they matter downstream.
- If the template emits software or runtime metadata, expose `software_versions` and
  `runtime_command` when appropriate.

### `run`

Use either:

- `run.command` for short, thin launchers
- `run.entry` for real scripts

Use `mode: direct` when the template should execute immediately with `linkar run`.

Use `mode: render` when the template should render a bundle that humans may inspect or edit before execution.

Rule of thumb:

- If the runtime logic is a short single command, `run.command` is fine.
- If the logic includes multiline shell flow, heredocs, nontrivial environment handling, or embedded Python, use `run.sh`.

For this pack, prefer `run.entry: run.sh` once the command stops being trivial.

## Organize The Runtime Files Well

A good template directory is easy to scan:

- `linkar_template.yaml` is the contract
- `run.sh` or `run.py` is the main execution entrypoint
- helper scripts have narrow, descriptive names
- static example or fallback files are explicit
- `README.md` explains inputs, behavior, outputs, and test commands

Avoid:

- putting large operational logic directly into YAML
- mixing many unrelated responsibilities into one huge shell script
- hiding critical behavior in undocumented helper files

## Prefer `run.py` Once Logic Becomes Real

For `izkf_pack`, a very effective pattern for medium or large templates is:

```text
templates/<template_id>/
  linkar_template.yaml
  run.sh
  run.py
  test.py
  optional config templates...
```

Recommended role split:

- `linkar_template.yaml` is the contract
- `run.sh` is a thin human-facing entrypoint
- `run.py` contains the actual runtime logic
- `test.py` executes `run.py` directly with mocked tools and temporary files

Use this when the template needs:

- parameter validation
- generated config files
- structured command assembly
- multiple runtime side effects
- cleanup logic
- runtime metadata outputs

Keep `run.sh` very small. A good default is:

```bash
#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${script_dir}/run.py"
```

This preserves the nice rendered-bundle workflow:

```bash
bash run.sh
```

while keeping the real logic in Python where it is easier to test and maintain.

## Record Runtime Metadata Explicitly

Do not assume future tooling should parse `run.sh` or `run.py` to reconstruct what happened.

For important templates, prefer writing explicit runtime metadata files.

Recommended pair:

- `software_versions.json`
- `runtime_command.json`

Keep them separate:

- `software_versions.json` records tools and versions
- `runtime_command.json` records the effective runtime command and resolved context

Suggested `runtime_command.json` fields:

- `template`
- `engine`
- `pipeline`
- `pipeline_version`
- `command`
- `command_pretty`
- `params`
- `artifacts`

This is especially useful for downstream reporting templates such as `methods`.

## How Binding Works

Bindings live at pack level in `linkar_pack.yaml`.

They can:

- set default `outdir`
- resolve parameter values from a function
- resolve parameter values from outputs of previous templates
- provide literal default values

Pattern examples:

```yaml
templates:
  nfcore_3mrnaseq:
    params:
      samplesheet:
        function: generate_nfcore_rnaseq_samplesheet_forward
      max_cpus:
        function: get_host_max_cpus

  dgea:
    params:
      salmon_dir:
        function: get_dgea_salmon_dir

  multiqc:
    params:
      input_dir:
        template: demultiplex
        output: results_dir
```

Binding functions are searched in `functions/<name>.py` and must define:

```python
def resolve(ctx):
    ...
    return value
```

## When To Add A Binding Function

Add a function when a parameter should come from:

- project history
- previous template outputs
- facility metadata APIs
- host-specific defaults
- generated helper files

Good binding candidates:

- samplesheets derived from a previous demultiplex run
- genome defaults resolved from request metadata
- output directories derived from input names
- project author names for reports

Avoid binding functions when:

- a static default in YAML is enough
- the value is a true user decision and should stay explicit

## How To Bind Parameters To Other Templates

Prefer explicit output chaining over fragile path guessing.

Good pattern:

- upstream template declares stable outputs
- downstream template binds to those outputs by template id and output key

Example:

```yaml
templates:
  downstream_template:
    params:
      input_dir:
        template: upstream_template
        output: results_dir
```

If the downstream parameter needs transformation, use a binding function instead of hardcoding assumptions into the downstream script.

Examples:

- find the latest FASTQ directory from `demultiplex.demux_fastq_files`
- derive organism from upstream `genome`
- reuse a project name or author block in reports

Best practices:

- Bind to semantically meaningful outputs, not arbitrary file paths.
- Keep cross-template coupling minimal and documented.
- If the binding depends on "latest run" behavior, make that clear in the function docstring and README.

## Template-Level `README.md`

Every template should have its own `README.md`.

Minimum contents:

- what the template does
- key parameters
- important outputs
- whether it is `direct` or `render`
- whether it uses pack bindings
- what upstream resources or repositories it depends on
- test commands

Useful structure:

```md
# <template_id>

Short description.

## Linkar interface

- important params
- important outputs
- render/direct behavior

## Bindings

- which params are usually resolved from `linkar_pack.yaml`
- required environment variables for facility bindings

## Runtime behavior

Explain the main execution flow.

## Test commands

Show both direct local test and Linkar-driven test commands.
```

Keep this README aligned with the actual implementation.

## Pack-Level `README.md`

When adding a new template, update the pack-level `README.md` if the template is:

- a major user-facing analysis entrypoint
- part of the normal workflow chain
- something users should discover from the front page

Examples that usually deserve README updates:

- new analysis pipeline wrappers
- new project-level reporting templates
- new export or archive workflows

Small internal helper templates may not need prominent front-page coverage, but if users are expected to run them directly, mention them.

## Testing Expectations

Every new template should have a `test.py` or `test.sh`.

Prefer `test.py` when:

- the template uses filesystem fixtures
- you need fake tools on `PATH`
- you need precise assertions on files and metadata

Prefer `test.sh` only for very small smoke tests.

### What To Test

At minimum:

- the template entrypoint runs successfully in a controlled test environment
- expected outputs are created
- important metadata files are created when applicable
- important runtime arguments are wired correctly

When the template has bindings, also test:

- explicit param behavior
- resolved/default behavior if practical
- failure messages for missing required upstream context

### Development-Phase Testing

Run the narrowest useful tests before handoff.

For template-local tests:

```bash
rtk python3 /home/ckuo/github/izkf_pack/templates/<template_id>/test.py
```

When possible, also run a Linkar-driven test from the Linkar repo:

```bash
cd /home/ckuo/github/linkar
rtk python3 -m pytest tests -k <template_id>
```

or:

```bash
cd /home/ckuo/github/linkar
rtk pixi run linkar test <template_id> --pack /home/ckuo/github/izkf_pack
```

Do not claim a template is done if you did not run any verification. If something cannot be tested locally, say so explicitly.

## Recommended Implementation Workflow

Use this order:

1. Study one or two existing templates with similar behavior.
2. Decide which parameters are explicit and which should be bound.
3. Draft `linkar_template.yaml`.
4. Add `run.sh` or `run.py`.
5. Add or update binding functions in `functions/` if needed.
6. Update `linkar_pack.yaml`.
7. Write `test.py`.
8. Update template `README.md`.
9. Update pack `README.md` if the template is user-facing.
10. Run the narrowest useful tests.
11. Review outputs and naming for downstream reuse.

## Output Naming Best Practices

Choose names that other templates can understand without reverse engineering.

Prefer names like:

- `results_dir`
- `fastq_dir`
- `demux_fastq_files`
- `multiqc_report`
- `salmon_dir`
- `software_versions`
- `methods_long`

Avoid vague names like:

- `output1`
- `final`
- `result_file`

## Software Version Metadata

If the template runs external software or depends on pinned upstream references, emit `software_versions.json` when practical.

This helps:

- methods generation
- provenance review
- debugging

Prefer recording:

- command-based versions
- pinned commit hashes for upstream repos
- important parameter-selected tool modes

When a template has more than one or two version entries, prefer a small
`software_versions_spec.yaml` alongside `run.sh` and call the shared
`functions/software_versions.py --spec ...` helper instead of embedding a custom
Python snippet in each template.

## Bioinformatics-Specific Advice

For analysis templates in this pack:

- keep facility-specific defaults out of the public parameter interface when possible
- prefer upstream pinned versions or commits for external repos
- treat samplesheets, references, and metadata-derived defaults as provenance-sensitive
- make important scientific decisions visible in params or output metadata
- avoid "magic" path assumptions unless documented and tested

If a template consumes outputs from a previous step:

- declare the upstream-facing output carefully in the producer
- document the expected chain in both READMEs
- prefer binding functions when project-history lookup is nontrivial

## Git Hygiene

If you were asked to implement a template and the work is complete:

- inspect the diff
- stage only the relevant files
- do not stage unrelated user changes
- make a focused commit if the user asked for commit-ready work or explicitly asked you to commit

Typical files to stage for a new template:

- `templates/<template_id>/linkar_template.yaml`
- `templates/<template_id>/run.sh` or `run.py`
- `templates/<template_id>/test.py`
- `templates/<template_id>/README.md`
- `functions/<new_binding>.py` if added
- `linkar_pack.yaml`
- `README.md` if updated

Example:

```bash
rtk git -C /home/ckuo/github/izkf_pack add \
  templates/<template_id> \
  functions/<new_binding>.py \
  linkar_pack.yaml \
  README.md
```

Commit only when appropriate:

```bash
rtk git -C /home/ckuo/github/izkf_pack commit -m "Add <template_id> Linkar template"
```

If the repository already contains unrelated changes, do not sweep them into your commit.

## Definition Of Done

A new template is ready when:

- the contract is clear
- outputs are explicit
- bindings are intentional
- tests pass or test limitations are clearly reported
- template `README.md` is updated
- pack `README.md` is updated when needed
- the diff is clean and reviewable

## Strong Defaults For Agents

When in doubt:

- copy the style of the closest existing `izkf_pack` template
- keep `linkar_template.yaml` declarative
- prefer `run.sh` for nontrivial execution logic
- expose fewer, better params
- use bindings for reusable inference
- test before handoff
- document the template where users will actually look
