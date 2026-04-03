# export_del

`export_del` is a direct Linkar action template that deletes an export project
from the facility export engine.

## Usage

```bash
linkar run export_del \
  --pack /home/ckuo/github/izkf_pack \
  --project-id project-123 \
  --confirm-delete true
```

Optional API override:

```bash
linkar run export_del \
  --pack /home/ckuo/github/izkf_pack \
  --project-id project-123 \
  --confirm-delete true \
  --export-engine-api-url http://genomics.rwth-aachen.de:9500/export
```

## Saved artifacts

This template writes only lightweight action metadata into the Linkar run:

- `results/delete_response.json`
- `results/export_project_id.txt`

It does not modify source data directories.
