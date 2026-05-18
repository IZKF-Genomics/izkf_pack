# methods_from_paths

Use an LLM to generate a publication-oriented Microsoft Word methods document from one or more
analysis files or directories.

This direct-mode template is intentionally thin. It scans folders, excludes binary and irrelevant
files, sends the readable evidence to an OpenAI-compatible LLM with a publication-methods prompt,
and writes one docx.

Typical usage:

```bash
linkar run methods_from_paths \
  --input-paths analysis/,qc/,scripts/ \
  --out-file Methods_project.docx
```

The main output is always available as:

- `results/methods.docx`

If `out_file` is an absolute path, the same docx is also written there. If `out_file` is relative,
it is written under the Linkar results directory. The selected location is recorded in
`results/out_file.txt`.

## Inputs

`input_paths` may point to files or directories. Directories are scanned recursively for common
analysis evidence:

- scripts and notebooks such as `.R`, `.py`, `.sh`, `.qmd`, `.ipynb`
- configuration and metadata files such as `.yaml`, `.yml`, `.json`, `.toml`, `.csv`, `.tsv`
- QC and report text such as `.md`, `.txt`, `.log`, `.html`

Large files, binary files, FASTQ/BAM/CRAM-style data files, `.pixi`, `.renv`, cache folders, and
other common non-method folders are skipped. Skipped files may still appear in the manifest as weak
context, but their content is not read.

## LLM configuration

This template requires LLM settings; it does not generate a rule-based methods draft when LLM
settings are missing. The standard setup is:

```bash
export LINKAR_LLM_API_KEY="..."
export LINKAR_LLM_BASE_URL="https://api.example.org/v1"
export LINKAR_LLM_MODEL="example-model"
```

The runner reads these environment variables directly:

- `LINKAR_LLM_API_KEY`
- `LINKAR_LLM_BASE_URL`
- `LINKAR_LLM_MODEL`

Resolution order is:

1. explicit template parameters for `llm_base_url` and `llm_model`
2. `LINKAR_LLM_API_KEY`, `LINKAR_LLM_BASE_URL`, and `LINKAR_LLM_MODEL`
3. `llm_config` for shared non-secret defaults or advanced setups

Keep secrets in environment variables. Use `llm_config` only for non-secret defaults unless you are
working in a private local context.

## `keep_intermediates`

The default behavior keeps the output tidy and writes only the docx plus `out_file.txt`. For review
or debugging:

```bash
linkar run methods_from_paths \
  --input-paths analysis/,qc/,scripts/ \
  --out-file Methods_project.docx \
  --keep-intermediates true
```

This additionally keeps:

- `methods_context.yaml`
- `methods_long.md`
- `methods_short.md`
- `methods_references.md`
- `methods_prompt.md`
- `methods_response.json`

## Test commands

```bash
python3 templates/methods_from_paths/test.py
```
