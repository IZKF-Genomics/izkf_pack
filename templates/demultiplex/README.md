# demultiplex

This Linkar template clones a pinned upstream `demultiplexing_prefect` checkout at execution time
instead of vendoring a snapshot into the pack.

## Upstream source

- repo: `https://github.com/chaochungkuo/demultiplexing_prefect`
- pinned commit: `c94cc9652af5d7beb5bd80e01d28bd1ae473e6ce`

Each rendered or executed run clones the upstream repository into the run directory, checks out the
pinned commit above, and launches the pipeline from that staged checkout.

## Linkar interface

Linkar owns the run directory, so the upstream `--outdir` parameter is mapped internally to
`${LINKAR_RESULTS_DIR}` and is not exposed as a template parameter.

Exposed parameters:

- `bcl_dir`
- `samplesheet`
- `use_api_samplesheet`
- `agendo_id`
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
`/data/fastq/<bcl-dir-name>` unless you pass an explicit `--outdir` value, and upstream
`--threads` uses 80% of the detected host CPUs unless you pass an explicit `--threads` value.

Not exposed anymore:

- `mode`
- `manifest_tsv`
- `in_fastq_dir`

Those belonged to the older wrapper, not the current upstream `main` CLI.

## Runtime behavior

The template keeps the execution logic in a standalone [run.sh](run.sh):

```bash
git clone --depth 1 https://github.com/chaochungkuo/demultiplexing_prefect ./demultiplexing_prefect
git -C ./demultiplexing_prefect fetch --depth 1 origin c94cc9652af5d7beb5bd80e01d28bd1ae473e6ce
git -C ./demultiplexing_prefect checkout c94cc9652af5d7beb5bd80e01d28bd1ae473e6ce
cd ./demultiplexing_prefect
pixi run demux-pipeline ...
```

`linkar_template.yaml` now points to `run.entry: run.sh`, and Linkar still renders the outer
launcher for render mode. That keeps the template contract small while the real shell logic stays in
one script that is easier to test and review. The rendered `run.sh` also writes
`software_versions.json` inline so it does not depend on helper scripts from the pack checkout.
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
2. facility API lookup at `/api/get/samplesheet/flowcell/{flowcell}` using `--flowcell-id` when provided, or a flowcell id derived from `--bcl-dir`
3. optional Agendo request-id fallback by `--agendo-id` only when the flowcell lookup returns 404
4. bundled template fallback [samplesheet.csv](samplesheet.csv) if the API lookup is unavailable or returns no record

That fallback file is only a generic placeholder. It is useful as a last-resort file default, but
it may not be correct for a real sequencing run.

Flowcell-only API lookup does not require `--agendo-id`:

```bash
linkar render demultiplex \
  --binding default \
  --bcl-dir /data/bcl/260407_NB501289_0992_AHLHGVBGYX \
  --flowcell-id HLHGVBGYX
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
