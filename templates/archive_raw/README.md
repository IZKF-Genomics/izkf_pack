# archive_raw

`archive_raw` archives raw sequencing run directories from `/data/raw` into the
facility archive tree under `/mnt/nextgen2/archive/raw`.

It uses a shared manifest root:

- `/data/shared/linkar_manifests/archive_raw_*.json`
- `/data/shared/linkar_manifests/archive_raw_*.log`

## Recommended usage

Dry run:

```bash
linkar run archive_raw --pack /home/ckuo/github/izkf_pack --dry-run true
```

Execute:

```bash
linkar run archive_raw --pack /home/ckuo/github/izkf_pack --yes true
```

`archive_raw` does not delete source runs.

## Key parameters

- `source_root`: raw run root, default `/data/raw`
- `target_root`: archive destination root
- `instrument_folders`: comma-separated instrument subdirectories to scan
- `yes`: confirm execution for non-dry runs
- `dry_run`: build the manifest and verification plan without copying data
- `cleanup`: whether to delete sources after verification, default `false`

## Outputs

- `results/manifest_path.txt`
- `results/log_path.txt`

## Test command

```bash
cd /home/ckuo/github/izkf_pack/templates/archive_raw
python3 test.py
```
