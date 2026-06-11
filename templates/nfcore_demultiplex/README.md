# nfcore_demultiplex

This template wraps `nf-core/demultiplex` for raw sequencer run folders while
keeping the final Nextflow command visible in `run.sh`.

It is intentionally opinionated:

- fixed pipeline revision: `1.7.1`
- fixed Nextflow engine via `NXF_VER=25.10.2`
- fixed execution profile: `docker`
- Illumina and 10x Genomics runs use `bclconvert`
- Element Biosciences AVITI runs use `bases2fastq`
- `raw_run_dir` is the only raw input directory parameter
- project-level FASTQ and QC views are hardlink-based
- AVITI runs skip nf-core's global MultiQC by default and rely on project-level MultiQC

## Linkar Interface

Exposed parameters:

- `raw_run_dir`
- `flowcell_samplesheet`
- `use_api_samplesheet`
- `agendo_id`
- `flowcell_id`
- `flowcell_lane`
- `merge_lanes`
- `platform`
- `demultiplexer`
- `skip_tools`
- `v1_schema`
- `project_multiqc`
- `allow_empty_fastq`
- `max_cpus`
- `max_memory`
- `demux_cpus`
- `falco_cpus`

With `--binding default`, the pack can resolve:

- `flowcell_samplesheet`
  - explicit `--flowcell-samplesheet` first
  - AVITI `raw_run_dir/RunManifest.csv` when present
  - Illumina facility API lookup via flowcell id, with `agendo_id` as request fallback
- `max_cpus` and `max_memory` from host capacity
- render `outdir` from `raw_run_dir`, under `/data/fastq` by default

`v1_schema` defaults to `true` because the facility Illumina samplesheets are
usually legacy IEM v1 / `[Data]` sheets. Set `--v1-schema false` for Illumina
v2 samplesheets.

Illumina samplesheets fetched from the facility APIs are staged as-is. The
template does not remove adapter settings by default; this avoids corrupting
valid bcl-convert settings such as `AdapterBehavior=trim` paired with
`AdapterRead1` / `AdapterRead2`.

`merge_lanes` defaults to `true` for Illumina bcl-convert runs. When no
specific `flowcell_lane` is requested, the template passes
`--no-lane-splitting true` so each sample gets merged FASTQs across lanes.

`max_cpus` is the total local CPU budget. `demux_cpus` defaults to `max_cpus`
and is used for `bases2fastq` / `bclconvert`. `falco_cpus` defaults to
`min(8, max_cpus / 4)` and is applied to each Falco task; Falco `maxForks` is
derived so concurrent Falco tasks stay within the total CPU budget.

## Platform Detection

`platform=auto` and `demultiplexer=auto` are the defaults.

Detection is conservative:

- `raw_run_dir/RunManifest.csv` -> `platform=aviti`, `demultiplexer=bases2fastq`
- Illumina markers such as `RunInfo.xml`, `InterOp/`, `RTAComplete.txt`, or
  `Data/Intensities/BaseCalls/` -> `platform=illumina`, `demultiplexer=bclconvert`
- otherwise the template fails and asks for `--platform` or `--demultiplexer`

Manual override examples:

```bash
linkar render nfcore_demultiplex \
  --binding default \
  --raw-run-dir /data/raw/260407_NB501289_0992_AHLHGVBGYX \
  --platform illumina
```

```bash
linkar render nfcore_demultiplex \
  --binding default \
  --raw-run-dir /data/raw/AVITI_RUN_001 \
  --platform aviti
```

## Runtime Behavior

The template follows the same user-facing launcher style as `nfcore_3mrnaseq`.

`run.py --prepare`:

- resolves platform and demultiplexer
- copies the demultiplexer-specific samplesheet to `flowcell_samplesheet.csv`
- writes `config/run_params.env`

The template does not render a generic `samplesheet.csv`. In single-flowcell
mode, `flowcell_samplesheet.csv` is the only samplesheet consumed by
`nf-core/demultiplex`.

`run.sh` contains the visible command:

```bash
pixi run nextflow run nf-core/demultiplex \
  -r 1.7.1 \
  -profile docker \
  -c nextflow.config \
  --flowcell_id "${FLOWCELL_ID}" \
  --flowcell_samplesheet flowcell_samplesheet.csv \
  --flowcell_path "${RAW_RUN_DIR}" \
  --outdir results \
  --demultiplexer "${DEMULTIPLEXER}" \
  --trim_fastq false \
  --remove_samplesheet_adapter "${REMOVE_SAMPLESHEET_ADAPTER}"
```

Users can edit the rendered `run.sh` directly before rerunning.

`remove_samplesheet_adapter` defaults to `false`. This preserves complete
bcl-convert adapter trimming settings in facility SampleSheets, especially when
`AdapterBehavior=trim` is present.

## Project-Level Views

After nf-core finishes, `build_project_views.py` parses the flowcell samplesheet
and writes one adoptable project view per `Sample_Project` / `Project` value:

```text
results/output/<project>/
├── .linkar/
│   └── meta.json
├── template_outputs.json
├── *.fastq.gz
└── qc/
    ├── input/
    └── multiqc/
        └── multiqc_report.html
```

FASTQs are hardlinked into each project directory. Matching QC and metrics files
are hardlinked under `qc/input`, then MultiQC is run per project when
`project_multiqc=true`. Hardlinks keep each project self-contained without
duplicating the underlying FASTQ bytes on disk.

After project views are built successfully, the native nf-core flowcell-level
folder `results/<flowcell_id>/` is removed. The project folders keep the real
FASTQ and QC files, while `pipeline_info/`, `samplesheet/`, reports, and
diagnostic CSV files remain at the top level.

Empty FASTQs are excluded from project views. By default, the template fails
with a clear diagnostic if empty FASTQs are detected after nf-core succeeds,
because empty FASTQs usually indicate wrong sample indexes or placeholder rows
in the flowcell samplesheet. Set `allow_empty_fastq=true` only for deliberate
edge cases.

The launcher pins `NXF_VER=25.10.2` by default because newer Nextflow/Groovy
combinations can fail while publishing `nf-core/demultiplex` 1.7.1 outputs with
`Unknown method invocation rightShift on UnixPath type`, even after all pipeline
tasks have completed successfully.

If that exact publish-only failure is detected after nf-core has reported a
successful pipeline completion, `run.sh` recovers the demultiplexed FASTQs from
the successful demultiplexer work directory before continuing to the project
views. Recovered FASTQs are hardlinked into `results/` so they survive
`linkar clean`. The recovery path requires the demultiplexer task to have
`.exitcode=0`; real demultiplexing failures still stop the run.

## Empty FASTQ Diagnostics

The launcher writes two small reports:

- `results/manifest_lint_report.csv`
- `results/empty_fastq_report.csv`

`manifest_lint_report.csv` warns about suspicious manifest rows such as
`ExampleSample_*` or placeholder indexes like `AAAAAAAAAA`.

`empty_fastq_report.csv` lists FASTQs where no read header could be read. When
nf-core fails with `startsWith() on null object`, `run.sh` automatically runs
the empty FASTQ diagnostic and prints the affected samples. The usual fix is to
correct the `Index1` / `Index2` values in `flowcell_samplesheet.csv`, or comment
out rows for samples that are not expected to have reads, then rerun:

```bash
bash run.sh -resume
```

Adopt one project from a mixed flowcell:

```bash
linkar project init \
  --name Project_A \
  --adopt /data/fastq/example_run/results/output/Project_A
```

## Test Commands

Direct local test:

```bash
cd templates/nfcore_demultiplex
python3 test.py
```

Through Linkar:

```bash
cd /path/to/linkar
pixi run linkar test nfcore_demultiplex --pack /path/to/izkf_pack
```
