# methods

Generate publication-oriented methods drafts from Linkar project history, template-specific catalog
entries, recorded software versions, and runtime command metadata.

This template is designed to synthesize:

- template-level scientific descriptions from [methods_catalog.yaml](/home/ckuo/github/izkf_pack/templates/methods/methods_catalog.yaml:1)
- project-level runtime context from `project.yaml`
- recorded `software_versions.json`
- recorded `runtime_command.json`
- optional LLM polishing through an OpenAI-compatible API

The template writes:

- `results/methods_context.yaml`
- `results/methods_long.md`
- `results/methods_short.md`
- `results/methods_references.md`
- `results/methods_prompt.md`
- `results/methods_response.json`

## Linkar interface

Exposed parameters:

- `project_dir`
- `style`
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

`methods` combines these sources into deterministic drafts first, and only then optionally asks an
LLM to polish the prose.

## LLM configuration

By default the template is deterministic and does not call any LLM.

When `use_llm=true`, settings can come from:

1. explicit template params such as `llm_base_url` and `llm_model`
2. `llm_config`, a YAML or JSON file
3. environment variables such as `LINKAR_LLM_BASE_URL`, `LINKAR_LLM_MODEL`, and `LINKAR_LLM_API_KEY`
4. a project-local default file at `.methods_llm.yaml`

Example `.methods_llm.yaml`:

```yaml
base_url: https://api.example.org/v1
model: gpt-5.4-mini
temperature: 0.2
api_key_env: OPENAI_API_KEY
```

The API key can be provided either through:

- `LINKAR_LLM_API_KEY`
- the environment variable named by `api_key_env`
- `api_key` in the config file

For safety, environment variables are still the preferred place for tokens.

## Runtime behavior

The template keeps a thin [run.sh](/home/ckuo/github/izkf_pack/templates/methods/run.sh:1) wrapper
for direct execution, while the real logic lives in
[run.py](/home/ckuo/github/izkf_pack/templates/methods/run.py:1).

`run.py`:

- loads `project.yaml`
- reads the methods catalog
- loads `software_versions.json` and `runtime_command.json` from recorded runs when available
- builds deterministic long and short methods drafts
- collects citations into `methods_references.md`
- writes the final LLM prompt used for polishing
- optionally calls an OpenAI-compatible chat completions API

## Test commands

Direct local test:

```bash
cd /home/ckuo/github/izkf_pack/templates/methods
pixi run test
```

Direct local execution:

```bash
cd /home/ckuo/github/izkf_pack/templates/methods
pixi run run-local -- --results-dir ./results --project-dir ..
```
