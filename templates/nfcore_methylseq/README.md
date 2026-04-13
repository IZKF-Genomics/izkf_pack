# nfcore_methylseq

This template provides an RRBS-first `nf-core/methylseq` wrapper for `izkf_pack`.

It is intentionally narrow in the first version:

- fixed pipeline revision: `4.2.0`
- fixed execution profile: `docker`
- no GPU support
- RRBS enabled by default because RRBS is the main methylation protocol used in the lab

## Linkar interface

Exposed parameters:

- `samplesheet`
- `genome`
- `agendo_id`
- `rrbs`
- `project_name`
- `max_cpus`
- `max_memory`

With `--binding default`, the pack can resolve:

- `samplesheet` from the latest `demultiplex.demux_fastq_files` outputs in the active project
- `genome` from Agendo organism metadata
- `project_name` from the active Linkar project name
- `max_cpus` and `max_memory` from host capacity

## Samplesheet generation

The default binding generates the `nf-core/methylseq` samplesheet from FASTQ names recorded by the
latest `demultiplex` run.

The generated columns are:

- `sample`
- `fastq_1`
- `fastq_2`
- `genome`

The samplesheet `genome` column is left blank and the template passes `--genome` explicitly on the
Nextflow command line.

## Runtime behavior

The template keeps the execution logic in a standalone [run.sh](/home/ckuo/github/izkf_pack/templates/nfcore_methylseq/run.sh:1).

That script:

- validates `genome` before launch
- records `software_versions.json`
- sets `--multiqc_title` from the Linkar project name
- passes `--rrbs` by default
- runs the fixed `nf-core/methylseq` invocation

## Test commands

Direct local test:

```bash
cd /home/ckuo/github/izkf_pack/templates/nfcore_methylseq
python3 test.py
```

Through Linkar:

```bash
cd /home/ckuo/github/linkar
pixi run linkar test nfcore_methylseq --pack /home/ckuo/github/izkf_pack
```
