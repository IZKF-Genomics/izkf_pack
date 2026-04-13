# archive_projects

`archive_projects` archives project directories from `/data/projects` into
`/mnt/nextgen2/archive/projects`.

It uses the shared manifest root:

- `/data/shared/linkar_manifests/archive_projects_*.json`
- `/data/shared/linkar_manifests/archive_projects_*.log`

By default, cleanup is enabled after successful verify.

## Key parameters

- `source_root`: source projects root, default `/data/projects`
- `target_root`: archive destination root
- `retention_days`: minimum project age before archiving
- `yes`: confirm execution for non-dry runs
- `dry_run`: build the manifest and verification plan without copying data
- `exclude_patterns`: comma-separated rsync exclude list

## Outputs

- `results/manifest_path.txt`
- `results/log_path.txt`

## Test command

```bash
cd /home/ckuo/github/izkf_pack/templates/archive_projects
python3 test.py
```
