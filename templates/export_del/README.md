# export_del

`export_del` is a direct Linkar action template that deletes an exported web
project from the facility export engine, including configured web backends such
as Apache, OwnCloud, and SFTP.

## Usage

```bash
linkar run export_del \
  --project-id project-123
```

Optional API override:

```bash
linkar run export_del \
  --project-id project-123 \
  --export-engine-api-url http://genomics.rwth-aachen.de:9500/export
```

To clean a specific export engine job instead of deleting by project name, pass
`--job-id`:

```bash
linkar run export_del \
  --job-id job-123
```

Deletion is enabled by default because invoking this template is already an
explicit delete action. To deliberately block execution in a rendered command,
set `--confirm-delete false`.

If your current directory is not using the active global pack, use `--project` or `--binding` according to your Linkar setup rather than `--pack`.

## Saved artifacts

This template writes only lightweight action metadata into the Linkar run:

- `results/delete_response.json`
- `results/export_job_id.txt`
- `results/export_project_id.txt`

It does not modify source data directories.
