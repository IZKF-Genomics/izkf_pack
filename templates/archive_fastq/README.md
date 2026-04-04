# archive_fastq

`archive_fastq` archives FASTQ run directories from `/data/fastq` into
`/mnt/nextgen2/archive/fastq`.

It uses the shared manifest root:

- `/data/shared/linkar_manifests/archive_fastq_*.json`
- `/data/shared/linkar_manifests/archive_fastq_*.log`

By default, cleanup is enabled after successful verify.
