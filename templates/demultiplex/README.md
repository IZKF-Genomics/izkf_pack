# demultiplex

This template clones the upstream `demultiplexing_prefect` repository into the rendered run
artifact as:

```text
demultiplexing_prefect/
```

and then runs its `cli.py` through `pixi`.

The runtime wrapper is intentionally explicit. The main step is visible in `run.sh`:

```bash
git clone "${repo_ref}" "${repo_dir}"
git -C "${repo_dir}" checkout "${revision}"
```

## Upstream source

- repo: `https://github.com/MoSafi2/demultiplexing_prefect`
- pinned revision: `940067c3efd02cf3ac44707fc490d5e16fa8a01e`

The run artifact keeps the cloned repo inside the rendered run directory so the exact implementation
used for the run remains inspectable.

## Entry points

- runtime: `run.sh`
- local test: `test.py`

## Parameters

The template exposes the upstream CLI contract through `linkar_template.yaml`:

- `mode`
- `qc_tool`
- `threads`
- `run_name`
- `bcl_dir`
- `samplesheet`
- `use_api_samplesheet`
- `agendo_id`
- `flowcell_id`
- `manifest_tsv`
- `in_fastq_dir`
- `contamination_tool`
- `kraken_db`
- `bracken_db`
- `fastq_screen_conf`

## API samplesheet integration

In demux mode, the template resolves the samplesheet in this order:

1. use explicit `samplesheet` if provided
2. otherwise, if `use_api_samplesheet=true`, fetch `samplesheet.csv` into the rendered run
3. otherwise fail because demux mode still requires a samplesheet

The API fetch uses:

- `GF_API_NAME`
- `GF_API_PASS`

from the environment. These are intentionally not exposed as template params, so credentials do not
end up in Linkar run metadata.

Optional controls:

- `flowcell_id`: override the flowcell id used for API lookup
- `agendo_id`: request-level fallback if the flowcell lookup is not found

## Test commands

Direct local test:

```bash
cd /Users/jovesus/github/izkf_genomics_pack/templates/demultiplex
python test.py
```

Through Linkar:

```bash
cd /Users/jovesus/github/linkar
pixi run linkar test demultiplex --pack /Users/jovesus/github/izkf_genomics_pack
```
