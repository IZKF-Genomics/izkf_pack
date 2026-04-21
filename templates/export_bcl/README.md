# export_bcl

Direct-run template for exporting a raw BCL run directory.

Unlike `export_demux`, this template does **not** write any sidecar metadata into the source run directory. The BCL folder stays untouched.

All export request and response artifacts are saved only in the Linkar action run `results/` directory:

- `export_job_spec.json`
- `export_job_spec.redacted.json`
- `export_response.json`
- `export_final_message.json`
- `export_job_id.txt`
- `export_bcl_summary.json`

Use `--dry-run true` to generate the redacted export spec without submitting anything.

## Key parameters

- `run_dir`: raw sequencing run directory
- `project_name`: recorded export project name
- `bcl_dir`: optional BCL directory override
- `export_engine_api_url`: export engine endpoint
- `export_username` and `export_password`: optional credential overrides
- `dry_run`: prepare but do not submit

## Test command

```bash
cd templates/export_bcl
python3 test.py
```
