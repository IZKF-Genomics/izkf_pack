# nfcore_3mrnaseq

This template provides a clean Linkar wrapper around the facility-specific `nf-core/rnaseq`
configuration used for 3' mRNA-seq runs.

It is intentionally opinionated:

- fixed pipeline revision: `3.26.0`
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

- `samplesheet` from the latest `nfcore_demultiplex.demux_fastq_files` or legacy `demultiplex.demux_fastq_files` outputs in the active project
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
latest `nfcore_demultiplex` or legacy `demultiplex` run.

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

- preserves unresolved genome placeholders so they are clearly editable before launch
- derives `effective_genome` from `spikein` when ERCC is present
- copies the resolved Linkar samplesheet to the fixed workspace path `samplesheet.csv`
- writes `config/run_params.env` with the resolved runtime values used by `run.sh`
- keeps pipeline version, profile, UMI, CPU, memory, and key nf-core arguments visible in the shell launcher

The template [nextflow.config](nextflow.config)
contains the shared genome references. It is copied as a static site config and is not rewritten by
`run.py`.

The [run.sh](run.sh) launcher is the stable user-facing entrypoint in both the source template and
rendered workspaces. It contains:

- `pixi install`
- the exact resolved `nextflow run nf-core/rnaseq ...` command
- fixed local input/output paths: `--input samplesheet.csv` and `--outdir results`
- `linkar collect` after successful execution

That means users can inspect the real command in plain shell and rerun the analysis later with:

```bash
./run.sh
```

If a user wants to add `-resume` or any other workflow flag, they can edit the rendered `run.sh`
directly.

Resolved parameters are stored in `config/run_params.env`. Rerendering the template refreshes that
file from Linkar bindings; manual reruns reuse it unless the user edits it.

## Runtime metadata

nf-core writes the authoritative runtime metadata under `results/pipeline_info/`. Linkar collects
`params_*.json` as the runtime command record and
`nf_core_rnaseq_software_mqc_versions.yml` as the software version record.

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
