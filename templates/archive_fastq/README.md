# archive_fastq

`archive_fastq` archives FASTQ run directories from `/data/fastq` into
`/mnt/nextgen2/archive/fastq`.

It uses the shared manifest root:

- `/data/shared/linkar_manifests/archive_fastq_*.json`
- `/data/shared/linkar_manifests/archive_fastq_*.log`

By default, cleanup is enabled after successful verify.

## Key parameters

- `source_root`: source FASTQ root, default `/data/fastq`
- `target_root`: archive destination root
- `retention_days`: minimum run age before archiving
- `yes`: confirm execution for non-dry runs
- `dry_run`: build the manifest and verification plan without copying data
- `exclude_patterns`: comma-separated rsync exclude list

## Outputs

- `results/manifest_path.txt`
- `results/log_path.txt`

## Test command

```bash
cd /home/ckuo/github/izkf_pack/templates/archive_fastq
python3 test.py
```
