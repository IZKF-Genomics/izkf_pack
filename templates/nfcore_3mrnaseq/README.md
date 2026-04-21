# nfcore_3mrnaseq

This template provides a clean Linkar wrapper around the facility-specific `nf-core/rnaseq`
configuration used for 3' mRNA-seq runs.

It is intentionally opinionated:

- fixed pipeline revision: `3.22.2`
- fixed execution profile: `docker`
- template-local `pixi.toml` provides `nextflow`
- shared genome references come from `nextflow.config`
- UMI handling is enabled automatically for the facility default UMI metadata label

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

For manual CLI use, this template also accepts boolean-style shorthands for the facility defaults:

- `--param umi=true` resolves to the facility default UMI metadata value
- `--param spikein=true` resolves to `ERCC RNA Spike-in Mix`

The same shorthand also accepts `yes`, `on`, and `1`. False-like values such as `false`, `no`, `off`, and `0` disable the setting.

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
`run.py`.

`run.py`:

- validates `genome` before launch
- derives `effective_genome` from `spikein` when ERCC is present
- writes a fully resolved rerunnable shell script with the exact `nextflow` command
- installs the template-local `pixi` environment and runs `nextflow` from it
- records `software_versions.json`
- records `runtime_command.json` with the effective Nextflow invocation and resolved runtime context
- enables UMI extraction flags for the facility default UMI metadata label
- writes a generated runtime `nextflow.config` and applies CPU / memory caps through `-c`
- runs the generated shell script

The template [nextflow.config](nextflow.config)
contains the shared genome references and runtime resource-limit placeholders used to produce the
final generated config under `results/`.

When Linkar renders this template, it asks `run.py` to write `./run.sh` in the rendered workspace.
That generated `run.sh` contains:

- `pixi install`
- the exact resolved `nextflow run nf-core/rnaseq ...` command

That means users can inspect the real command in plain shell and rerun the analysis later with:

```bash
./run.sh
```

If a user wants to add `-resume` or any other workflow flag, they can edit the rendered `run.sh`
directly.

The repository copy of [run.sh](run.sh) is
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
cd templates/nfcore_3mrnaseq
pixi run run-local
pixi run test
```

Through Linkar:

```bash
cd /path/to/linkar
pixi run linkar test nfcore_3mrnaseq --pack /path/to/izkf_pack
```
