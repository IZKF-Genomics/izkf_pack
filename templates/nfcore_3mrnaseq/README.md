# nfcore_3mrnaseq

This template provides a clean Linkar wrapper around the facility-specific `nf-core/rnaseq`
configuration used for 3' mRNA-seq runs.

It is intentionally opinionated:

- fixed pipeline revision: `3.22.2`
- fixed execution profile: `docker`
- template-local `pixi.toml` provides `nextflow`
- shared genome references come from [nextflow.config](/home/ckuo/github/izkf_pack/templates/nfcore_3mrnaseq/nextflow.config:1)
- UMI handling is enabled automatically for the known Takara QuantSeq kit phrase

## Linkar interface

Exposed parameters:

- `samplesheet`
- `genome`
- `agendo_id`
- `umi`
- `spikein`
- `max_cpus`
- `max_memory`

With `--binding default`, the pack can resolve:

- `samplesheet` from the latest `demultiplex.demux_fastq_files` outputs in the active project
- `genome` from Agendo organism metadata
- `umi` from Agendo UMI metadata
- `spikein` from Agendo spike-in metadata
- `max_cpus` and `max_memory` from host capacity

## Samplesheet generation

The default binding generates the `nf-core/rnaseq` samplesheet from FASTQ names recorded by the
latest `demultiplex` run.

The generated columns are:

- `sample`
- `fastq_1`
- `fastq_2`
- `strandedness`

For this template, the generated samplesheet uses `forward` strandedness.

## Runtime behavior

The actual runtime logic lives in
[run.py](/home/ckuo/github/izkf_pack/templates/nfcore_3mrnaseq/run.py:1).

`run.py`:

- validates `genome` before launch
- derives `effective_genome` from `spikein` when ERCC is present
- writes a fully resolved rerunnable shell script with the exact `nextflow` command
- installs the template-local `pixi` environment and runs `nextflow` from it
- records `software_versions.json`
- records `runtime_command.json` with the effective Nextflow invocation and resolved runtime context
- enables UMI extraction flags for the known Takara QuantSeq kit phrase
- writes a generated runtime `nextflow.config` and applies CPU / memory caps through `-c`
- runs the generated shell script

The template [nextflow.config](/home/ckuo/github/izkf_pack/templates/nfcore_3mrnaseq/nextflow.config:1)
contains the shared genome references and runtime resource-limit placeholders used to produce the
final generated config under `results/`.

When Linkar renders this template, it asks `run.py` to write `./run.sh` in the rendered workspace.
That generated `run.sh` contains:

- `pixi install`
- the exact resolved `nextflow run nf-core/rnaseq ...` command
- optional `-resume` support for reruns

That means users can inspect the real command in plain shell and rerun the analysis later with:

```bash
./run.sh
./run.sh -resume
```

The repository copy of [run.sh](/home/ckuo/github/izkf_pack/templates/nfcore_3mrnaseq/run.sh:1) is
kept as a small developer wrapper. It writes `resolved_run.sh` locally so the tracked template file
is not overwritten during template development.

## Runtime metadata

This template writes:

- `software_versions.json`
- `runtime_command.json`

`runtime_command.json` is the preferred downstream source when another template needs to understand
the actual runtime command and resolved parameters.

## Test commands

Direct local test:

```bash
cd /home/ckuo/github/izkf_pack/templates/nfcore_3mrnaseq
pixi run run-local
pixi run test
```

Through Linkar:

```bash
cd /home/ckuo/github/linkar
pixi run linkar test nfcore_3mrnaseq --pack /home/ckuo/github/izkf_pack
```
