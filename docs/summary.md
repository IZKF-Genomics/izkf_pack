# summary in izkf_pack

The [`summary`](../templates/summary/README.md) template generates
bioinformatics analysis summaries from Linkar project history.

It is not just a text summarizer. It combines:

- recorded project runs from `project.yaml`
- template-level scientific notes from
  [`templates/summary/summary_catalog.yaml`](../templates/summary/summary_catalog.yaml)
- runtime artifacts such as `software_versions.json` and
  `runtime_command.json`
- optional metadata API enrichment
- optional LLM polishing for the final prose

## Main outputs

The template writes these files into `summary/results/`:

- `summary_long.md`
- `summary_long.html`
- `summary_short.md`
- `summary_short.html`
- `summary_references.md`
- `summary_context.yaml`
- `summary_prompt.md`
- `summary_response.json`

## Long vs short

The intended split is:

- `summary_long.*`
  Detailed, structured background for the project in execution order. This is
  the place for parameters, software versions, recorded commands, reference
  details, and citations.

- `summary_short.*`
  A cleaner manuscript-style condensation of the long version. It should read
  like a reviewable analysis summary, not like raw run metadata.

In this pack, the short version should be derived from the long version, not
written as an unrelated summary.

## Where the content comes from

The analysis summary template uses several sources in order:

1. project history in `project.yaml`
2. template outputs recorded in run metadata
3. `results/software_versions.json`
4. `results/runtime_command.json`
5. template-level catalog text and citations
6. optional metadata API details for assay context

For nf-core workflows, important settings such as genome, UMI handling, and
spike-in context should prefer the rendered or recorded command when available.
This helps the analysis summary text reflect what was actually run rather than only what
was present in upstream metadata.

## LLM usage

The template can use an LLM to polish the output, but the deterministic draft
comes first.

That means:

- the pack still produces useful analysis summary text without an LLM
- the LLM should refine structure and readability rather than invent workflow
  details
- if LLM configuration is missing, the template falls back to deterministic
  output and records the reason in `summary_response.json`

## Recommended usage

The `summary` template is a render-first visible workspace. The recommended
bundle is:

```bash
linkar run summary \
  --outdir ./summary \
  --refresh
```

This keeps the visible workspace in `./summary` and overwrites
`summary/results/*` on reruns.

## Design goals for pack maintenance

When editing analysis summary generation in this pack:

- keep the long version detailed but tidy
- keep the short version readable for manuscript use
- preserve real technical names and versions
- use citations that correspond to actual tools or methods in use
- avoid internal authoring text or pack-maintainer language in the final prose

## Related docs

- [software_versions.md](software_versions.md)
- [template_outputs.md](template_outputs.md)
- [export.md](export.md)
