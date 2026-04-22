# nfcore_scrnaseq

This template provides an `izkf_pack`-native wrapper around `nf-core/scrnaseq` for
single-cell RNA-seq runs.

It expects shared reference genomes, STAR indices, and optional Cell Ranger
references to be maintained by the companion facility repository
[`genomics-assets`](https://github.com/IZKF-Genomics/genomics-assets).

The first version is intentionally conservative:

- fixed pipeline revision: `4.1.0`
- fixed execution profile: `docker`
- template-local `pixi.toml` provides `nextflow`
- `aligner` is required and has no default
- the first implementation supports `star` and `cellranger`
- `protocol=auto` is only allowed when `aligner=cellranger`
- shared STAR references can be used for genomes such as zebrafish without requiring a 10x Cell Ranger reference

## Linkar interface

Exposed parameters:

- `samplesheet`
- `genome`
- `agendo_id`
- `aligner`
- `protocol`
- `expected_cells`
- `skip_cellbender`
- `star_index`
- `cellranger_index`
- `max_cpus`
- `max_memory`

With `--binding default`, the pack can resolve:

- `samplesheet` from the latest `demultiplex.demux_fastq_files` outputs in the active project
- `genome` from Agendo organism metadata when `agendo_id` is available; otherwise render falls back to an editable placeholder and a guarded `run.sh`
- `max_cpus` and `max_memory` from host capacity

## Samplesheet staging

The default binding generates the `nf-core/scrnaseq` samplesheet from FASTQ names recorded by the
latest `demultiplex` run.

The staged samplesheet always contains:

- `sample`
- `fastq_1`
- `fastq_2`

If `expected_cells` is set and the input sheet does not already define it, the runtime adds the
optional `expected_cells` column when writing the workspace-local `samplesheet.csv`.

## Runtime behavior

The actual runtime logic lives in [run.py](run.py).

`run.py`:

- validates `genome`, `aligner`, and `protocol` before launch
- stages a rerunnable `samplesheet.csv` in the rendered workspace
- resolves shared FASTA / GTF / STAR / Cell Ranger references for supported genomes
- writes a rerunnable shell script with the full resolved `nextflow` command line
- writes `params.yaml` and a generated runtime `nextflow.config` in the rendered workspace
- records `software_versions.json`
- records `runtime_command.json` with the effective Nextflow invocation and resolved runtime context
- selects a preferred downstream `.h5ad` result and links it as `selected_matrix.h5ad`

The template-local [nextflow.config](nextflow.config) carries a facility genome registry keyed by
labels such as `GRCh38`, `GRCm39`, and `GRCz11`. The rendered launcher therefore keeps the visible
CLI short and uses `--genome <label>` by default instead of printing long reference paths unless an
explicit override such as `--cellranger-index` was provided.

This is an intentional facility wrapper convenience. The upstream nf-core/scrnaseq documentation
recommends using pipeline parameters via the CLI or `-params-file` and reserving `-c` for
infrastructure tweaks. Here the custom config is used as a local label-to-reference registry so the
generated command remains readable while still resolving to the facility-managed references.

When Linkar renders this template, it asks `run.py` to write `./run.sh` in the rendered workspace.
That generated `run.sh` contains:

- `pixi install`
- the exact resolved `nextflow run nf-core/scrnaseq ...` command with explicit nf-core parameters instead of only `-params-file`

That means users can inspect the real command in plain shell and rerun the analysis later with:

```bash
./run.sh
```

If a user wants to add `-resume` or another workflow flag, they can edit the rendered `run.sh`
directly.

The repository copy of [run.sh](run.sh) is kept as a small developer wrapper so template development
does not overwrite the tracked file.

## Outputs

- `results/software_versions.json`
- `results/runtime_command.json`
- `results/matrix_selection.json`
- `selected_matrix.h5ad`

`runtime_command.json` is the preferred downstream source when another template needs to understand
the actual runtime command and resolved parameters.

## Test commands

Direct local test:

```bash
cd templates/nfcore_scrnaseq
pixi run run-local
pixi run test
```

Through Linkar:

```bash
cd /path/to/linkar
pixi run linkar test nfcore_scrnaseq --pack /path/to/izkf_pack
```
