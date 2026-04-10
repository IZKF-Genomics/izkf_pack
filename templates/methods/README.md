# methods

Generate project-level methods drafts from Linkar project history.

The template reads `project.yaml`, inspects recorded template params, outputs, and runtime metadata,
then writes:

- `results/methods_context.yaml`
- `results/methods_long.md`
- `results/methods_short.md`
- `results/methods_references.md`
- `results/methods_prompt.md`
- `results/methods_response.json`

By default the output is deterministic and does not call any LLM.

Optional LLM polishing uses an OpenAI-compatible chat completions API. Keep the token out of
project metadata by setting it as an environment variable:

```bash
export LINKAR_LLM_API_KEY="..."
export LINKAR_LLM_BASE_URL="https://api.example.org/v1"
export LINKAR_LLM_MODEL="example-model"
linkar run methods --param use_llm=true
```

Template params can override `llm_base_url` and `llm_model`, but the API key is read only from
`LINKAR_LLM_API_KEY`.
