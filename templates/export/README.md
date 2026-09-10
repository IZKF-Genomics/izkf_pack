# export

This template migrates the BPM `export` workflow into a Linkar pack template.

It keeps the export mapping table as data, and makes the old BPM hook chain explicit:

- [build_export_bundle.py](build_export_bundle.py) builds `export_job_spec.json`, metadata files, and summary files from project history.
- [submit_export.py](submit_export.py) submits the prepared spec to the export engine and records submission outputs.

## Current behavior

`linkar run export`:

- rebuilds the export bundle into `results/` by default
- generates new credentials by default unless credential reuse is requested
- stores credentials only in `results/export_credentials.json` with owner-only (`0600`) permissions
- submits the prepared spec with `POST /export`
- polls `GET /export/{job_id}/poll`, then reads `GET /export/final_message/{job_id}`
- records submission artifacts into `results/`

`linkar run export --prepare-only`:

- rebuilds the export bundle into `results/`
- writes a credential-free `results/export_job_spec.json`, the private credentials file, and related metadata
- does not contact the export engine

`linkar run export --refresh-export true`:

- rebuilds the export bundle from the current project history
- reuses saved username/password credentials while rebuilding
- submits `results/export_refresh_spec.json` to the existing export job with `POST /export/{job_id}/refresh`
- polls `GET /export/{job_id}/poll`, then reads `GET /export/final_message/{job_id}`
- preserves the existing job id, username, password, and download link through the export engine refresh endpoint

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

Default run behavior:

```bash
linkar run export
```

This rebuilds `results/export_job_spec.json`, generates a new credential pair,
stores that pair privately, and submits the export. Credentials are injected into
the API request in memory and are not retained in the public job spec.

To choose a password explicitly without placing it in shell arguments or Linkar metadata, set it
only for the command environment:

```bash
read -rsp 'Export password: ' LINKAR_EXPORT_PASSWORD
export LINKAR_EXPORT_PASSWORD
linkar run export
unset LINKAR_EXPORT_PASSWORD
```

Useful alternate modes:

```bash
linkar run export --prepare-only
linkar run export --refresh-export true
linkar run export --reuse-spec
linkar run export --reuse-credentials
linkar render export
linkar render export --reuse-credentials
```

Credential reuse looks for a complete username/password pair in this order:

- `results/export_credentials.json`
- legacy `results/export_submission.json`
- legacy `results/export_job_spec.json`
- legacy export template params in `project.yaml`

`--reuse-spec` submits the current `results/export_job_spec.json`. If it finds credentials in an
older spec, it migrates them into the private credentials file and rewrites the public spec without them.
`--reuse-credentials` rebuilds the spec but preserves saved credentials.
`--prepare-only` performs the selected preparation mode without submission.
`--refresh-export true` rebuilds the spec, reuses saved credentials automatically, and updates the existing export in place.

Export engine endpoints:

- Create: `POST /export`
- Refresh: `POST /export/{job_id}/refresh`
- Status: `GET /export/{job_id}/poll`
- Final delivery message: `GET /export/final_message/{job_id}`

You can also prepare without submission:

```bash
python3 run.py --project-dir "${LINKAR_PROJECT_DIR:-..}" --template-dir . --results-dir ./results --prepare-only true --export-engine-api-url http://127.0.0.1:9500
```

For direct script usage, inspect the available options with:

```bash
python3 run.py --help
python3 build_export_bundle.py --help
python3 submit_export.py --help
```

Generated artifacts include:

- `results/export_job_spec.json`
- `results/export_credentials.json` with mode `0600`; intentionally omitted from the Linkar output contract
- `results/export_refresh_spec.json` when refreshing
- `results/metadata_context.yaml`
- `results/metadata_raw.json`
- `results/metadata_normalized.yaml`
- `results/project_summary.md`
- `results/summary_context.yaml`
- `results/export_state.json` after submission or refresh

Passwords are removed from terminal output, `export_submission.json`, and
`export_final_message.txt`. Those public artifacts retain non-secret status, URLs, and usernames;
password occurrences in API messages are replaced with `[REDACTED]`. Authorized operators can read
the private credentials file directly when delivery credentials are needed.

## Notes

- At runtime the template prefers `LINKAR_PROJECT_DIR`, which Linkar exports automatically for project-backed runs and renders. Outside Linkar, it falls back to `..`.
- The vendored [export_mapping.table.yaml](export_mapping.table.yaml) has been normalized for the current `izkf_pack` template ids and outputs. Repeated template runs are namespaced by their rendered folder names such as `nfcore_liver`, `nfcore_bile_duct`, `DGEA_Liver`, or `DGEA_Bile_Duct`.
- Analysis summary generation is now Linkar-native and is built from local project history through [build_export_bundle.py](build_export_bundle.py), not through BPM runtime hooks.
