# software_versions in izkf_pack

`izkf_pack` uses a two-level model for software version tracking:

- template-level specs stored in the pack
- runtime JSON outputs generated in each rendered or executed workspace

This is why files such as
`templates/scverse_scrna_prep/software_versions_spec.yaml` and
`templates/nfcore_methylseq/software_versions_spec.yaml` should stay in the
repository even though `software_versions.json` is generated at runtime.

## The model

The checked-in spec file answers:

- which tools should be probed
- which parameters or environment-backed values should be recorded
- which static version labels should be emitted even if no command needs to run

The generated JSON answers:

- what versions were actually resolved for this run or workspace

## Execution flow

Many templates call the shared helper:

- [`functions/software_versions.py`](../functions/software_versions.py)

Typical pattern:

```bash
python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"
```

The spec is read at execution time, and the JSON file is written into the
workspace or results directory.

## Why keep the spec in the pack

Keeping `software_versions_spec.yaml` in the pack has a few advantages:

- the version policy is version-controlled
- templates stay easy to review without reading large shell fragments
- multiple templates can follow the same pattern consistently
- tests can verify that the template still records the expected tools and
  parameters
- downstream templates such as `methods` can rely on a standard
  `software_versions.json` artifact

## What should go into a spec

Good candidates:

- core execution tools such as `pixi`, `python`, `quarto`, `R`, or `nextflow`
- template parameters that matter for methods reporting
- static labels that help interpret the run later

Poor candidates:

- ephemeral file paths
- values that are already better captured in `runtime_command.json`
- metadata that belongs in `run_info.yaml` instead

## Relationship to methods and export

The `methods` template reads `software_versions.json` when available and uses it
to populate software/version statements in generated methods text.

The `export` template can also include these runtime artifacts in exported
bundles, so the JSON output is part of the provenance chain even though the spec
itself lives in the pack.

## When to avoid a spec file

You might skip `software_versions_spec.yaml` only when a template has a very
custom runtime and it is clearer to call
`functions/software_versions.py --command ... --static ...` inline.

In practice, the spec file is usually the better maintenance choice for this
pack.
