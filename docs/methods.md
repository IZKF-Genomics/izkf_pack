# methods in izkf_pack

The [`methods`](../templates/methods/README.md) template generates
publication-oriented method descriptions from Linkar project history.

It is not just a text summarizer. It combines:

- recorded project runs from `project.yaml`
- template-level scientific notes from
  [`templates/methods/methods_catalog.yaml`](../templates/methods/methods_catalog.yaml)
- runtime artifacts such as `software_versions.json` and
  `runtime_command.json`
- optional metadata API enrichment
- optional LLM polishing for the final prose

## Main outputs

The template writes these files into `methods/results/`:

- `methods_long.md`
- `methods_long.html`
- `methods_short.md`
- `methods_short.html`
- `methods_references.md`
- `methods_context.yaml`
- `methods_prompt.md`
- `methods_response.json`

## Long vs short

The intended split is:

- `methods_long.*`
  Detailed, structured background for the project in execution order. This is
  the place for parameters, software versions, recorded commands, reference
  details, and citations.

- `methods_short.*`
  A cleaner manuscript-style condensation of the long version. It should read
  like a publication methods section, not like raw run metadata.

In this pack, the short version should be derived from the long version, not
written as an unrelated summary.

## Where the content comes from

The methods template uses several sources in order:

1. project history in `project.yaml`
2. template outputs recorded in run metadata
3. `results/software_versions.json`
4. `results/runtime_command.json`
5. template-level catalog text and citations
6. optional metadata API details for assay context

For nf-core workflows, important settings such as genome, UMI handling, and
spike-in context should prefer the rendered or recorded command when available.
This helps the methods text reflect what was actually run rather than only what
was present in upstream metadata.

## LLM usage

The template can use an LLM to polish the output, but the deterministic draft
comes first.

That means:

- the pack still produces useful methods text without an LLM
- the LLM should refine structure and readability rather than invent workflow
  details
- if LLM configuration is missing, the template falls back to deterministic
  output and records the reason in `methods_response.json`

## Recommended usage

The `methods` template is a render-first visible workspace. The recommended
bundle is:

```bash
linkar run methods \
  --outdir ./methods \
  --refresh
```

This keeps the visible workspace in `./methods` and overwrites
`methods/results/*` on reruns.

## Design goals for pack maintenance

When editing methods generation in this pack:

- keep the long version detailed but tidy
- keep the short version readable for manuscript use
- preserve real technical names and versions
- use citations that correspond to actual tools or methods in use
- avoid internal authoring text or pack-maintainer language in the final prose

## Related docs

- [software_versions.md](software_versions.md)
- [template_outputs.md](template_outputs.md)
- [export.md](export.md)
