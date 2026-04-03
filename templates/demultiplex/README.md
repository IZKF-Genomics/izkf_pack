# demultiplex

This Linkar template clones the upstream `MoSafi2/demultiplexing_prefect` repository at execution
time instead of vendoring a snapshot into the pack.

## Upstream source

- repo: `https://github.com/MoSafi2/demultiplexing_prefect`
- branch: `main`

Each rendered or executed run clones the upstream repository into the run directory and launches the
pipeline from that fresh checkout.

## Linkar interface

Linkar owns the run directory, so the upstream `--outdir` parameter is mapped internally to
`${LINKAR_RESULTS_DIR}` and is not exposed as a template parameter.

Exposed parameters:

- `bcl_dir`
- `samplesheet`
- `qc_tool`
- `contamination_tool`
- `threads`
- `run_name`
- `kraken_db`
- `bracken_db`
- `fastq_screen_conf`

Not exposed anymore:

- `mode`
- `use_api_samplesheet`
- `agendo_id`
- `flowcell_id`
- `manifest_tsv`
- `in_fastq_dir`

Those belonged to the older wrapper, not the current upstream `main` CLI.

## Runtime behavior

The template declares one shell command directly in `linkar_template.yaml`:

```bash
git clone --depth 1 https://github.com/MoSafi2/demultiplexing_prefect ./demultiplexing_prefect
cd ./demultiplexing_prefect
pixi run python -m demux_pipeline.cli ...
```

Linkar renders that command into `run.sh`, so the rendered run directory contains a single launcher
that clones upstream when you execute it.

## Samplesheet resolution

When you run with `--binding default`, `samplesheet` resolves in this order:

1. explicit `--samplesheet`
2. facility API lookup using `GF_API_NAME` and `GF_API_PASS`
3. bundled template fallback [samplesheet.csv](/home/ckuo/github/izkf_pack/templates/demultiplex/samplesheet.csv) if the API returns 404 / no record

That fallback file is only a generic placeholder. It is useful as a last-resort file default, but
it may not be correct for a real sequencing run.

## Test commands

Direct local test:

```bash
cd /home/ckuo/github/izkf_pack/templates/demultiplex
python test.py
```

Through Linkar:

```bash
cd /home/ckuo/github/linkar
pixi run linkar test demultiplex --pack /home/ckuo/github/izkf_pack
```
