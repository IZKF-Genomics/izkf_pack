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
