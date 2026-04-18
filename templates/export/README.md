# export

This template migrates the BPM `export` workflow into a Linkar pack template.

It keeps the export mapping table as data, and makes the old BPM hook chain explicit:

- [build_export_bundle.py](/home/ckuo/github/izkf_pack/templates/export/build_export_bundle.py) builds `export_job_spec.json`, metadata files, and methods files from project history.
- [submit_export.py](/home/ckuo/github/izkf_pack/templates/export/submit_export.py) submits the prepared spec to the export engine and records submission outputs.

## Current behavior

`linkar run export`:

- builds the export bundle into `results/` if `results/export_job_spec.json` does not already exist
- submits the prepared spec
- records submission artifacts into `results/`

`linkar render export`:

- renders the template bundle
- prepares `results/export_job_spec.json` and related metadata files during render
- does not submit anything to the export engine

After rendering, inspect or edit:

```bash
cd /path/to/project/export
less results/export_job_spec.json
```

If you want to rebuild the bundle manually:

```bash
python3 build_export_bundle.py --project-dir "${LINKAR_PROJECT_DIR:-..}" --template-dir . --results-dir ./results
```

The launcher uses the prepared spec by default:

```bash
./run.sh
```

You can also prepare without submission:

```bash
python3 run.py --project-dir "${LINKAR_PROJECT_DIR:-..}" --template-dir . --results-dir ./results --dry-run true --export-engine-api-url http://127.0.0.1:9500
```

Generated artifacts include:

- `results/export_job_spec.json`
- `results/metadata_context.yaml`
- `results/metadata_raw.json`
- `results/metadata_normalized.yaml`
- `results/project_methods.md`
- `results/methods_context.yaml`

## Notes

- At runtime the template prefers `LINKAR_PROJECT_DIR`, which Linkar exports automatically for project-backed runs and renders. Outside Linkar, it falls back to `..`.
- The vendored [export_mapping.table.yaml](/home/ckuo/github/izkf_pack/templates/export/export_mapping.table.yaml) has been normalized for the current `izkf_pack` template ids and outputs. Repeated template runs are namespaced by their rendered folder names such as `nfcore_liver`, `nfcore_bile_duct`, `DGEA_Liver`, or `DGEA_Bile_Duct`.
- Methods generation is now Linkar-native and is built from local project history through [build_export_bundle.py](/home/ckuo/github/izkf_pack/templates/export/build_export_bundle.py), not through BPM runtime hooks.
