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
