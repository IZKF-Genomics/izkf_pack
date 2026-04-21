# nfcore_methylseq

This template provides an RRBS-first `nf-core/methylseq` wrapper for `izkf_pack`.

It is intentionally narrow in the first version:

- fixed pipeline revision: `4.2.0`
- fixed execution profile: `docker`
- template-local `pixi.toml` provides `nextflow`
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

The template keeps a thin [run.sh](run.sh)
wrapper for direct execution, but the actual runtime logic lives in
[run.py](run.py).

`run.py`:

- validates `genome` before launch
- installs the template-local `pixi` environment and runs `nextflow` from it
- records `software_versions.json`
- records `runtime_command.json` with the effective Nextflow invocation and resolved runtime context
- sets `--multiqc_title` from the Linkar project name
- passes `--rrbs` by default
- writes a generated runtime `nextflow.config` and applies CPU / memory caps through `-c`
- runs the fixed `nf-core/methylseq` invocation

The template [nextflow.config](nextflow.config)
also reuses shared FASTA references under `/data/ref_genomes`. Commented `bismark_index` paths are
included as placeholders for future centralized Bismark indices, and `fasta_index` is likewise
kept commented until shared `.fai` files are available.

## Test commands

Direct local test:

```bash
cd templates/nfcore_methylseq
pixi run run-local
pixi run test
```

Through Linkar:

```bash
cd /path/to/linkar
pixi run linkar test nfcore_methylseq --pack /path/to/izkf_pack
```
