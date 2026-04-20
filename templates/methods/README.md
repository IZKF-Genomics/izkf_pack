# methods

Generate publication-oriented methods drafts from Linkar project history, template-specific catalog
entries, recorded software versions, and runtime command metadata.

This template is designed to synthesize:

- template-level scientific descriptions from [methods_catalog.yaml](methods_catalog.yaml)
- project-level runtime context from `project.yaml`
- recorded `software_versions.json`
- recorded `runtime_command.json`
- LLM polishing through an OpenAI-compatible API, with deterministic fallback when settings are missing

The template writes:

- `results/methods_context.yaml`
- `results/methods_long.md`
- `results/methods_long.html`
- `results/methods_short.md`
- `results/methods_short.html`
- `results/methods_references.md`
- `results/methods_prompt.md`
- `results/methods_response.json`

## Linkar interface

The `methods` template is a render-first workspace. In a project, the recommended visible bundle is
`./methods`, not `.linkar/runs/...`.

Typical usage:

```bash
linkar run methods \
  --outdir ./methods \
  --refresh
```

or inspect first:

```bash
linkar render methods \
  --outdir ./methods

cd methods
bash run.sh
cd ..
linkar collect ./methods
```

Rerunning with the same visible bundle overwrites `methods/results/*` with the latest generated
drafts.

Exposed parameters:

- `project_dir`
- `style`
- `metadata_api_url`
- `use_llm`
- `llm_config`
- `llm_base_url`
- `llm_model`
- `llm_temperature`

## Catalog-driven design

The methods catalog now acts as template-level scientific guidance. Each template entry can provide:

- a human-readable label
- a short summary
- a method core sentence
- detailed interpretation hints
- important parameters to surface
- parameter explanations
- command interpretation hints
- tools and citations

The runtime side then contributes:

- recorded template params from `project.yaml`
- recorded runtime command metadata from `runtime_command.json`
- software and reference versions from `software_versions.json`
- Linkar runtime status from `.linkar/runtime.json`
- optional project-level assay metadata from the Agendo combined metadata API when an `agendo_id` is present in project history

When repeated templates appear in one project, the methods generator uses the
run-specific `params.name` when available, otherwise the rendered folder name,
to disambiguate sections such as `Differential gene expression analysis: Liver`
and `Differential gene expression analysis: Bile Duct`.

For templates that do not explicitly publish `software_versions` in
`project.yaml`, the methods generator also falls back to
`<run_dir>/results/software_versions.json` when present.

`methods` combines these sources into deterministic drafts first, and only then optionally asks an
LLM to polish the prose.

## LLM configuration

By default the template attempts LLM polishing. If the API key, base URL, or model is missing, it falls back to the deterministic drafts and records the reason in `methods_response.json`.

The standard user-facing setup is to define all three environment variables:

```bash
export LINKAR_LLM_API_KEY="..."
export LINKAR_LLM_BASE_URL="https://api.example.org/v1"
export LINKAR_LLM_MODEL="gpt-5.4-mini"
```

Resolution order is:

1. explicit template params for `llm_base_url` and `llm_model`
2. environment variables `LINKAR_LLM_API_KEY`, `LINKAR_LLM_BASE_URL`, and `LINKAR_LLM_MODEL`
3. `llm_config`, a YAML or JSON file
4. a project-local default file at `.methods_llm.yaml`

This means users should normally define URL, model, and API key in the environment, while config
files remain an optional fallback for shared non-secret defaults or advanced setups.

Example `.methods_llm.yaml`:

```yaml
base_url: https://api.example.org/v1
model: gpt-5.4-mini
temperature: 0.2
api_key_env: OPENAI_API_KEY
```

The API key can still come from:

- `LINKAR_LLM_API_KEY`
- the environment variable named by `api_key_env`
- `api_key` in the config file

For safety and predictability, environment variables are the recommended default for all three user
settings: token, URL, and model.

## Runtime behavior

The template keeps a thin [run.sh](run.sh) wrapper
for direct execution, while the real logic lives in
[run.py](run.py).

`run.py`:

- loads `project.yaml`
- reads the methods catalog
- resolves `agendo_id` from recorded project history and fetches combined project metadata when available
- loads `software_versions.json` and `runtime_command.json` from recorded runs when available
- builds deterministic long and short methods drafts
- collects citations into `methods_references.md`
- writes the final LLM prompt used for polishing
- optionally calls an OpenAI-compatible chat completions API

## Test commands

Direct local test:

```bash
cd templates/methods
pixi run test
```

Direct local execution:

```bash
cd templates/methods
pixi run run-local -- --results-dir ./results --project-dir ..
```
