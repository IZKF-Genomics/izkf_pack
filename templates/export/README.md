# export

This template migrates the BPM `export` workflow into a Linkar pack template.

It keeps the export mapping table as data, and makes the old BPM hook chain explicit:

- [build_export_bundle.py](build_export_bundle.py) builds `export_job_spec.json`, metadata files, and summary files from project history.
- [submit_export.py](submit_export.py) submits the prepared spec to the export engine and records submission outputs.

## Quick start

Create the first export or submit the already prepared specification:

```bash
linkar run export
```

Linkar chooses the safe action automatically:

- if no specification exists, it prepares one
- if a specification exists, it uses it without overwriting it
- if no saved job ID exists, it creates the export
- if a saved job ID exists, it updates that export
- updates keep the existing job ID, username, password, and publisher links

When project outputs or report mappings have changed, rebuild the specification explicitly:

```bash
linkar run export --refresh
```

## Review before submitting

To rebuild the specification for review without contacting the Export Engine:

```bash
linkar run export --refresh --prepare
less export/results/export_job_spec.json
```

Running the normal command afterward creates or updates the export.

## What the command does

The template:

- preserves an existing `results/export_job_spec.json` unless `--refresh` or `--new` is used
- stores credentials only in `results/export_credentials.json` with owner-only (`0600`) permissions
- creates with `POST /export`, or updates saved state with `POST /export/{job_id}/refresh`
- polls `GET /export/{job_id}/poll`, then reads `GET /export/final_message/{job_id}`
- records submission artifacts into `results/`
- waits for a newly updated persistent job record and treats that record as authoritative, so a stale `/poll` or final-message response cannot make a failed refresh appear successful

The public job specification never contains the password. The export service preserves credentials
when updating an existing job.

## Advanced and recovery options

Most users do not need these options:

```bash
# Recover local state by selecting a known server-side job.
linkar run export --job-id JOB_ID

# Create a new identity and credentials instead of updating saved state.
linkar run export --new

# Redact the password from terminal output.
linkar run export --hide-password
```

`--new` rebuilds the specification and credentials, but it never deletes an existing export. If the
saved export is still active, the command stops before changing local credentials. Use it only after
the previous export has been cleaned or when an operator has explicitly instructed you to create a
new identity.

`--job-id` is a recovery option. During normal operation Linkar reads the job ID from
`results/export_state.json` or `results/export_job_id.txt` automatically.

## Rendering without running

`linkar render export`:

- renders the template bundle
- prepares `results/export_job_spec.json` and related metadata files during render
- does not submit anything to the export engine

After rendering, inspect or edit:

```bash
cd /path/to/project/export
less results/export_job_spec.json
```

To choose a password explicitly without placing it in shell arguments or Linkar metadata, set it
only for the first export command environment:

```bash
read -rsp 'Export password: ' LINKAR_EXPORT_PASSWORD
export LINKAR_EXPORT_PASSWORD
linkar run export
unset LINKAR_EXPORT_PASSWORD
```

The export command prints the real password in the terminal `Access Credentials` and
`JSON Patch for MS Planner` sections by default so the block can be copied to MS Teams. Use
`--hide-password` when running in CI, a shared terminal, or a screen-sharing session.
Public result artifacts remain redacted, and the complete credentials remain stored in
`export_credentials.json` with mode `0600`.

The private username and password live only in `results/export_credentials.json`.
Normal updates preserve that file; `--new` replaces it with a new pair.

Export engine endpoints:

- Create: `POST /export`
- Refresh: `POST /export/{job_id}/refresh`
- Refresh status source of truth: `GET /export/{job_id}` (new `updated_at` generation)
- Status: `GET /export/{job_id}/poll`
- Final delivery message: `GET /export/final_message/{job_id}`

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

For `mirna_differential`, the export layout intentionally separates reusable analysis results and
configuration from the standalone report:

- `2_Processed_data/mirna_differential[/<instance>]/results`
- `2_Processed_data/mirna_differential[/<instance>]/config`
- `3_Reports/mirna_differential[/<instance>]`

The optional instance level is added only when the rendered folder name differs from the template
id. Workspace source files, Pixi environments, and caches are not exported.

For `cellranger_multi`, the export preserves the distinction between executed outputs,
user-edited configuration, and generated execution inputs:

- `2_Processed_data/cellranger_multi[/<instance>]/results` contains the original per-GEM-well
  Cell Ranger output trees, including per-biological-sample outputs when hashing or another
  supported multiplexing configuration was used.
- `2_Processed_data/cellranger_multi[/<instance>]/config` records the GEM-well library manifest,
  Cell Ranger settings, optional hashtag assignments, and optional custom Feature Reference.
- `2_Processed_data/cellranger_multi[/<instance>]/generated` records the exact resolved Feature
  Reference and per-GEM-well multi CSV files passed to Cell Ranger.

The reader-facing report index is intentionally curated. It links the complete results folder,
the automatic cross-sample QC overview, uniquely labelled GEM-well and biological-sample HTML summaries, the configuration folder, and
the exact resolved Feature Reference. Matrices, metric CSV files, multiplexing diagnostics,
Loupe Browser files, runtime metadata, and generated multi CSV files remain available inside the
exported directory tree but are not expanded into individual report links. A header-only
`sample_assignments.csv` means that antibody hashtag assignment was not configured. The optional
instance level is added when the rendered folder name differs from `cellranger_multi`; template
source code, checked-in barcode catalogs, environments, and caches are not exported.

Passwords are displayed in terminal output by default but always removed from
`export_submission.json` and `export_final_message.txt`. Passing `--hide-password` redacts
the terminal output as well. Public artifacts retain non-secret status, URLs, and usernames;
password occurrences in saved API messages are replaced with `[REDACTED]`. Authorized operators
can also read the private credentials file directly.

## Notes

- At runtime the template prefers `LINKAR_PROJECT_DIR`, which Linkar exports automatically for project-backed runs and renders. Outside Linkar, it falls back to `..`.
- The vendored [export_mapping.table.yaml](export_mapping.table.yaml) has been normalized for the current `izkf_pack` template ids and outputs. Repeated template runs are namespaced by their rendered folder names such as `nfcore_liver`, `nfcore_bile_duct`, `DGEA_Liver`, or `DGEA_Bile_Duct`.
- Analysis summary generation is now Linkar-native and is built from local project history through [build_export_bundle.py](build_export_bundle.py), not through BPM runtime hooks.

## Template layout for maintainers

The eight tracked files have separate responsibilities:

- `linkar_template.yaml`: Linkar parameters, outputs, and runtime commands
- `run.py`: create-versus-update orchestration and user-facing CLI
- `build_export_bundle.py`: metadata, credentials, summary, and job-spec construction
- `submit_export.py`: Export Engine HTTP submission, polling, and result recording
- `export_common.py`: mapping and summary functions shared by the builder and tests
- `export_mapping.table.yaml`: reviewable data-driven export policy
- `test.py`: end-to-end template tests with a local mock Export Engine
- `README.md`: user and maintainer documentation

Keeping the build and HTTP layers separate avoids turning `run.py` into a single large module and
lets mapping policy remain editable without changing Python code. `__pycache__/` is ignored runtime
cache and is not part of the tracked template.
