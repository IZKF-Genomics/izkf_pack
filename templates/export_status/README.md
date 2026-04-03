# export_status

`export_status` is a direct Linkar action template that queries the facility export
engine for the current status of a known export `job_id`.

## Usage

```bash
linkar run export_status \
  --pack /home/ckuo/github/izkf_pack \
  --job-id job-123
```

Optional API override:

```bash
linkar run export_status \
  --pack /home/ckuo/github/izkf_pack \
  --job-id job-123 \
  --export-engine-api-url http://genomics.rwth-aachen.de:9500/export
```

## Saved artifacts

This template only writes lightweight action metadata into the Linkar run:

- `results/export_status.json`
- `results/export_job_id.txt`

It does not modify source data directories.
