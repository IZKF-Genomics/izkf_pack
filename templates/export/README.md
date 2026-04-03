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

- renders the template bundle only
- does not build the export spec automatically, because Linkar render does not execute template code

After rendering, you can prepare the bundle manually:

```bash
cd /path/to/project/export
python build_export_bundle.py --project-dir .. --template-dir . --results-dir ./results
```

Then inspect or edit:

- `results/export_job_spec.json`
- `results/metadata_context.yaml`
- `results/metadata_raw.json`
- `results/metadata_normalized.yaml`
- `results/project_methods.md`
- `results/methods_context.yaml`

and finally run:

```bash
./run.sh
```

## Notes

- This template assumes it lives directly under a Linkar project root, so it can read `../project.yaml`.
- The vendored [export_mapping.table.yaml](/home/ckuo/github/izkf_pack/templates/export/export_mapping.table.yaml) has been normalized for the current `izkf_pack` template ids and outputs.
- Methods generation prefers `bpm.core.agent_methods` when available. If that import fails, the template writes a fallback note instead of aborting.
