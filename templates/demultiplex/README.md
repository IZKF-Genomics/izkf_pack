# demultiplex

This Linkar template clones a pinned upstream `demultiplexing_prefect` checkout at execution time
instead of vendoring a snapshot into the pack.

## Upstream source

- repo: `https://github.com/MoSafi2/demultiplexing_prefect`
- pinned commit: `72c1550bc7c2941dbb9993ee60e4ff9a18bd36d4`

Each rendered or executed run clones the upstream repository into the run directory, checks out the
pinned commit above, and launches the pipeline from that staged checkout.

## Linkar interface

Linkar owns the run directory, so the upstream `--outdir` parameter is mapped internally to
`${LINKAR_RESULTS_DIR}` and is not exposed as a template parameter.

Exposed parameters:

- `bcl_dir`
- `platform`
- `samplesheet`
- `use_api_samplesheet`
- `flowcell_id`
- `qc_tool`
- `contamination_tool`
- `threads`
- `kraken_db`
- `bracken_db`
- `fastq_screen_conf`

Pack defaults:

- render `outdir` resolves through `get_demultiplex_render_outdir`
- `get_demultiplex_render_outdir` returns `/data/fastq/<basename(bcl_dir)>` by default
- `threads` resolves through `get_host_max_cpus`
- `get_host_max_cpus` returns `max(1, int(os.cpu_count() * 0.8))`

That means a normal `linkar render demultiplex ...` run through `izkf_pack` renders into
`/data/fastq/<run-folder-name>` unless you pass an explicit `--outdir` value, and upstream
`--threads` uses 80% of the detected host CPUs unless you pass an explicit `--threads` value.

Not exposed anymore:

- `mode`
- `manifest_tsv`
- `in_fastq_dir`

Those belonged to the older wrapper, not the current upstream `main` CLI.

## Runtime behavior

The template keeps the execution logic in a standalone [run.sh](run.sh):

```bash
git clone --depth 1 https://github.com/MoSafi2/demultiplexing_prefect ./demultiplexing_prefect
git -C ./demultiplexing_prefect fetch --depth 1 origin 72c1550bc7c2941dbb9993ee60e4ff9a18bd36d4
git -C ./demultiplexing_prefect checkout 72c1550bc7c2941dbb9993ee60e4ff9a18bd36d4
cd ./demultiplexing_prefect
pixi run demux-pipeline --platform ... --input-dir ...
```

`linkar_template.yaml` now points to `run.entry: run.sh`, and Linkar still renders the outer
launcher for render mode. That keeps the template contract small while the real shell logic stays in
one script that is easier to test and review. The rendered `run.sh` writes
`software_versions.json` through the shared pack helper and the template-level
`software_versions_spec.yaml`.
After demultiplexing, it normalizes directory permissions under `results/output` to `775` so
sample-project subdirectories match the surrounding output directories. When `Sample_Project`
is present, Linkar captures raw FASTQs from `results/output/<Sample_Project>/` and project-local
QC and contamination outputs from `results/output/<Sample_Project>/qc/`.

The template also writes adoptable project metadata directly inside each project output folder:

```text
results/output/<Sample_Project>/
├── .linkar/
│   └── meta.json
├── template_outputs.json
├── *.fastq.gz
└── qc/
```

Both `.linkar/meta.json` and `template_outputs.json` identify the adopted slice as a
`demultiplex` template result and include the same project-local outputs, including
`demux_fastq_files`. They also include project-local `declared_outputs` so
`linkar project init --adopt` can refresh the adopted slice without replacing those outputs with an
empty result set. This keeps project initialization and downstream bindings consistent whether
Linkar reads the project metadata file or the template outputs contract.

Use that project folder when one demultiplex run contains several projects but you want a Linkar
project history for just one `Sample_Project`:

```bash
linkar project init \
  --name Project_A \
  --adopt /path/to/processed_runs/example_run/results/output/Project_A
```

## Samplesheet resolution

When you run with `--binding default`, `samplesheet` resolves in this order:

1. explicit `--samplesheet`
2. facility API lookup at `/api/get/samplesheet/flowcell/{flowcell}` using `--flowcell-id` when provided
3. when `--flowcell-id` is omitted, derive the lookup key from `--bcl-dir`: the final Illumina folder component without its leading `A`, or `FlowcellID` from AVITI `RunParameters.json`
4. safely extract the primary manifest from the returned ZIP review bundle and cache the complete bundle, evidence, and README under `~/.linkar/api_samplesheets/<flowcell>/<bundle-sha256>/`

API authentication, lookup, ZIP validation, and primary-manifest selection errors stop rendering.
The bundled [samplesheet.csv](samplesheet.csv) is a generic placeholder used only when
`--no-use-api-samplesheet` is explicitly selected; it may not be correct for a real run.

An explicit flowcell override remains available for unusual run folders:

```bash
linkar render demultiplex \
  --binding default \
  --bcl-dir /data/bcl/260407_NB501289_0992_AHLHGVBGYX \
  --flowcell-id HLHGVBGYX
```

For AVITI runs, set the platform explicitly. The default binding reads `FlowcellID` from
`<run>/RunParameters.json`, queries the facility API, and does not use `<run>/RunManifest.csv`:

```bash
linkar render demultiplex \
  --binding default \
  --platform aviti \
  --bcl-dir /data/raw/AVITI_RUN_001
```

## Test commands

Direct local test:

```bash
cd templates/demultiplex
python test.py
```

Through Linkar:

```bash
cd /path/to/linkar
pixi run linkar test demultiplex --pack /path/to/izkf_pack
```
