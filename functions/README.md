# Binding Functions

Binding functions let the pack resolve template parameters at render or run time. Linkar calls each function with the active context and expects a single value in return.

These functions should stay small, predictable, and easy to debug. If a function needs reusable logic, put that logic in a private helper module such as `_agendo_common.py` or `_dgea_common.py`.

## Public Functions

### `get_api_samplesheet`

Source: [`get_api_samplesheet.py`](get_api_samplesheet.py)

Resolves the demultiplexing samplesheet. It prefers an explicit `samplesheet` parameter, can query a configured metadata API when `use_api_samplesheet=true`, and falls back to the template-level bundled samplesheet when no API result is available.

Environment variables:

- `GF_API_NAME`
- `GF_API_PASS`
- `GF_API_BASE_FLOWCELL`
- `GF_API_BASE_REQUEST`

### `get_demultiplex_render_outdir`

Source: [`get_demultiplex_render_outdir.py`](get_demultiplex_render_outdir.py)

Builds the default render output directory for the `demultiplex` template from the basename of `bcl_dir`.

Environment variables:

- `IZKF_DEMULTIPLEX_RENDER_ROOT`

### `get_demultiplex_fastq_dir`

Source: [`get_demultiplex_fastq_dir.py`](get_demultiplex_fastq_dir.py)

Finds the sample FASTQ directory from the latest recorded `demultiplex.demux_fastq_files` output in the current project. It ignores undetermined reads when possible and raises a clear error if the recorded FASTQ files span ambiguous directories.

### `generate_nfcore_rnaseq_samplesheet_forward`

Source: [`generate_nfcore_rnaseq_samplesheet_forward.py`](generate_nfcore_rnaseq_samplesheet_forward.py)

Generates an nf-core samplesheet from the latest recorded demultiplexed read pairs. It writes a cached samplesheet under the Linkar cache directory and returns that generated path.

Environment variables:

- `LINKAR_HOME`

### `generate_nfcore_methylseq_samplesheet`

Source: [`generate_nfcore_methylseq_samplesheet.py`](generate_nfcore_methylseq_samplesheet.py)

Generates an `nf-core/methylseq` samplesheet from the latest recorded demultiplexed FASTQ pairs. It writes a cached samplesheet under the Linkar cache directory and returns that generated path.

Environment variables:

- `LINKAR_HOME`

### `generate_nfcore_3mrnaseq_samplesheet`

Source: [`generate_nfcore_3mrnaseq_samplesheet.py`](generate_nfcore_3mrnaseq_samplesheet.py)

Generates an nf-core samplesheet by scanning the latest demultiplex results directory for paired reads. This is kept for compatibility with workflows that prefer directory-based discovery instead of the recorded file list.

Environment variables:

- `LINKAR_HOME`

### `get_agendo_genome`

Source: [`get_agendo_genome.py`](get_agendo_genome.py)

Reads request metadata and maps organism labels to supported genome identifiers. If no supported mapping exists, it returns a placeholder that makes the rendered launcher clearly editable before execution.

Environment variables:

- `GF_API_NAME`
- `GF_API_PASS`
- `GF_API_BASE_REQUEST_METADATA`
- `LINKAR_HOME`

### `get_agendo_umi`

Source: [`get_agendo_umi.py`](get_agendo_umi.py)

Reads UMI metadata from the request metadata API when an `agendo_id` is available. Returns an empty string when no request id is provided.

Environment variables:

- `GF_API_NAME`
- `GF_API_PASS`
- `GF_API_BASE_REQUEST_METADATA`
- `LINKAR_HOME`

### `get_agendo_spikein`

Source: [`get_agendo_spikein.py`](get_agendo_spikein.py)

Reads spike-in metadata from the request metadata API when an `agendo_id` is available. Returns an empty string when no request id is provided.

Environment variables:

- `GF_API_NAME`
- `GF_API_PASS`
- `GF_API_BASE_REQUEST_METADATA`
- `LINKAR_HOME`

### `get_host_max_cpus`

Source: [`get_host_max_cpus.py`](get_host_max_cpus.py)

Returns 80 percent of detected CPUs, with a minimum of one CPU. This gives workflow templates a safe host-aware default without hardcoding a machine profile.

### `get_host_max_memory`

Source: [`get_host_max_memory.py`](get_host_max_memory.py)

Returns 80 percent of detected host memory as a Nextflow-friendly value such as `128GB`. It reads `/proc/meminfo` on Linux and falls back to `sysctl` on other POSIX hosts.

### `get_project_name`

Source: [`get_project_name.py`](get_project_name.py)

Returns the active Linkar project name. Useful for template metadata such as report titles and MultiQC titles.

### `get_dgea_salmon_dir`

Source: [`get_dgea_salmon_dir.py`](get_dgea_salmon_dir.py)

Returns the latest upstream `salmon_dir` output from a recorded RNA-seq workflow so the DGEA template can locate quantification results.

### `get_dgea_samplesheet`

Source: [`get_dgea_samplesheet.py`](get_dgea_samplesheet.py)

Returns the upstream samplesheet parameter from a recorded RNA-seq workflow so the DGEA template can reuse the same sample metadata.

### `get_dgea_organism`

Source: [`get_dgea_organism.py`](get_dgea_organism.py)

Maps upstream genome or organism metadata to the organism value expected by the DGEA workspace.

### `get_dgea_application`

Source: [`get_dgea_application.py`](get_dgea_application.py)

Returns the upstream template id as the application label for DGEA reports.

### `get_dgea_name`

Source: [`get_dgea_name.py`](get_dgea_name.py)

Returns the active Linkar project name for use in DGEA report titles.

### `get_dgea_authors`

Source: [`get_dgea_authors.py`](get_dgea_authors.py)

Reads author metadata from the active Linkar project and returns a comma-separated author string for DGEA reports.

### `software_versions`

Source: [`software_versions.py`](software_versions.py)

Writes standardized `software_versions.json` files from command outputs and static metadata. Workflow templates can record versions locally, and the `methods` template can aggregate those records into publication-ready methods drafts.

CLI example:

```bash
python3 functions/software_versions.py \
  --output results/software_versions.json \
  --command "python=python3 --version" \
  --static "workflow=example"
```

## Internal Helpers

### `_agendo_common`

Source: [`_agendo_common.py`](_agendo_common.py)

Shared metadata API and cache helpers for the Agendo-related binding functions. It is not referenced directly from `linkar_pack.yaml`.

### `_dgea_common`

Source: [`_dgea_common.py`](_dgea_common.py)

Shared project-history utilities for DGEA binding functions. It is not referenced directly from `linkar_pack.yaml`.

## Tests

Run the function tests from the pack root:

```bash
python3 functions/test_get_api_samplesheet.py
```
