# Linkar Genomics Pack

This repository is a Linkar pack for routine sequencing data operations. It keeps reusable workflow templates, site-specific binding functions, and read-only discovery helpers in one place so a project can be assembled from small, inspectable steps.

The pack is intentionally practical:

- `templates/` contains runnable Linkar templates.
- `functions/` contains binding functions that resolve parameters from project history, host resources, metadata APIs, or generated helper files.
- `discovery/` contains read-only helpers for finding projects, sequencing runs, references, and processed run folders.
- `linkar_pack.yaml` wires selected templates to default binding functions.

## Install

Clone the pack and register it as a global Linkar pack:

```bash
cd ~/github/
gh repo clone IZKF-Genomics/izkf_pack
linkar config pack add ~/github/izkf_pack/
```

After this, Linkar can find the pack without passing `--pack` each time.

## Quick Start

From a project directory:

```bash
linkar project init --name example_project
linkar pack add /path/to/genomics_pack --id genomics --binding default
linkar project view
```

Render a template when you want to inspect or edit the generated launcher before execution:

```bash
linkar render demultiplex --param bcl_dir=/data/raw_runs/example_run
cd /data/processed_runs/example_run
bash run.sh
```

Run a direct action when it is safe to execute immediately:

```bash
linkar run methods --param use_llm=false
```

## Common Tasks

### Run Demultiplexing

Use this when starting from a raw sequencing run folder.

```bash
linkar render demultiplex \
  --param bcl_dir=/data/raw_runs/example_run
```

Then inspect and execute the rendered launcher:

```bash
cd /data/processed_runs/example_run
bash run.sh
```

Useful follow-up checks:

```bash
linkar project adopt-run /data/processed_runs/example_run
linkar project view
```

### Run Basic 3' mRNA-seq Analysis

Use this after demultiplexing has been recorded in the active project. The default binding can generate the nf-core samplesheet and resolve common metadata.

```bash
linkar render nfcore_3mrnaseq \
  --param agendo_id=EXAMPLE_REQUEST_ID
```

Then inspect and execute:

```bash
cd nfcore_3mrnaseq
bash run.sh
```

### Run Differential Gene Expression Workspace

Use this after the 3' mRNA-seq template has produced quantification outputs.

```bash
linkar render dgea
cd dgea
bash run.sh
```

The rendered workspace is meant to remain editable. Review the generated inputs and reports before treating the results as final.

### Run Methods Generation

Use this after one or more analysis runs have been adopted into `project.yaml`.

```bash
linkar run methods --param use_llm=false
```

Optional LLM polishing uses an OpenAI-compatible API. Keep secrets in the environment, not in `project.yaml`:

```bash
export LINKAR_LLM_API_KEY="..."
export LINKAR_LLM_BASE_URL="https://api.example.org/v1"
export LINKAR_LLM_MODEL="example-model"
linkar run methods --param use_llm=true
```

### Run Project Export

Use this after the project contains the runs and reports you want to publish.

```bash
linkar render export
cd export
less results/export_job_spec.json
bash run.sh
```

The render step prepares `results/export_job_spec.json` so it can be reviewed before submission.

## Templates

| Template | Purpose | Details |
| --- | --- | --- |
| [`demultiplex`](templates/demultiplex/linkar_template.yaml) | Clone and run the pinned demultiplexing workflow, writing processed outputs under `results/`. | [README](templates/demultiplex/README.md) |
| [`nfcore_3mrnaseq`](templates/nfcore_3mrnaseq/linkar_template.yaml) | Run the site-specific `nf-core/rnaseq` wrapper for 3' mRNA-seq projects. | [README](templates/nfcore_3mrnaseq/README.md) |
| [`dgea`](templates/dgea/linkar_template.yaml) | Create and run an editable R/Quarto differential expression workspace. | [README](templates/dgea/README.md) |
| [`cellranger_atac`](templates/cellranger_atac/linkar_template.yaml) | Discover ATAC samples, run `cellranger-atac count`, and optionally aggregate libraries. | [README](templates/cellranger_atac/README.md) |
| [`methods`](templates/methods/linkar_template.yaml) | Generate long and short project methods drafts from Linkar project history. | [README](templates/methods/README.md) |
| [`export`](templates/export/linkar_template.yaml) | Build and submit a project export bundle from recorded project outputs. | [README](templates/export/README.md) |
| [`export_demux`](templates/export_demux/linkar_template.yaml) | Export an ad hoc demultiplexing run outside a full Linkar project. | [README](templates/export_demux/README.md) |
| [`export_bcl`](templates/export_bcl/linkar_template.yaml) | Export a raw sequencing run without writing metadata into the source folder. | [README](templates/export_bcl/README.md) |
| [`export_status`](templates/export_status/linkar_template.yaml) | Query the export engine status for an existing export job. | [README](templates/export_status/README.md) |
| [`export_del`](templates/export_del/linkar_template.yaml) | Delete an export project from the export engine after explicit confirmation. | [README](templates/export_del/README.md) |
| [`archive_raw`](templates/archive_raw/linkar_template.yaml) | Archive raw sequencing run folders with a manifest log. | [README](templates/archive_raw/README.md) |
| [`archive_fastq`](templates/archive_fastq/linkar_template.yaml) | Archive processed sequencing run folders with a manifest log and optional cleanup. | [README](templates/archive_fastq/README.md) |
| [`archive_projects`](templates/archive_projects/linkar_template.yaml) | Archive project folders with a manifest log and optional cleanup. | [README](templates/archive_projects/README.md) |

## Binding Functions

The default binding in [`linkar_pack.yaml`](linkar_pack.yaml) uses Python functions from [`functions/`](functions/README.md). These functions are small by design: each returns one parameter value for one Linkar render/run context.

| Function | Purpose | Details |
| --- | --- | --- |
| [`get_api_samplesheet`](functions/get_api_samplesheet.py) | Resolve a demultiplexing samplesheet from an explicit value, metadata API, or bundled fallback. | [functions README](functions/README.md#get_api_samplesheet) |
| [`get_demultiplex_render_outdir`](functions/get_demultiplex_render_outdir.py) | Derive the default demultiplex render directory from the raw run folder name. | [functions README](functions/README.md#get_demultiplex_render_outdir) |
| [`get_demultiplex_fastq_dir`](functions/get_demultiplex_fastq_dir.py) | Resolve the sample FASTQ directory from recorded demultiplex outputs. | [functions README](functions/README.md#get_demultiplex_fastq_dir) |
| [`generate_nfcore_rnaseq_samplesheet_forward`](functions/generate_nfcore_rnaseq_samplesheet_forward.py) | Generate an nf-core samplesheet from demultiplexed read pairs recorded in project history. | [functions README](functions/README.md#generate_nfcore_rnaseq_samplesheet_forward) |
| [`generate_nfcore_3mrnaseq_samplesheet`](functions/generate_nfcore_3mrnaseq_samplesheet.py) | Generate an nf-core samplesheet from the latest demultiplex results directory. | [functions README](functions/README.md#generate_nfcore_3mrnaseq_samplesheet) |
| [`get_agendo_genome`](functions/get_agendo_genome.py) | Map metadata API organism values to supported genome identifiers. | [functions README](functions/README.md#get_agendo_genome) |
| [`get_agendo_umi`](functions/get_agendo_umi.py) | Resolve UMI metadata for nf-core runs. | [functions README](functions/README.md#get_agendo_umi) |
| [`get_agendo_spikein`](functions/get_agendo_spikein.py) | Resolve spike-in metadata for nf-core runs. | [functions README](functions/README.md#get_agendo_spikein) |
| [`get_host_max_cpus`](functions/get_host_max_cpus.py) | Use 80 percent of detected host CPUs as a safe default. | [functions README](functions/README.md#get_host_max_cpus) |
| [`get_host_max_memory`](functions/get_host_max_memory.py) | Use 80 percent of detected host memory as a safe default. | [functions README](functions/README.md#get_host_max_memory) |
| [`get_dgea_salmon_dir`](functions/get_dgea_salmon_dir.py) | Resolve the latest upstream Salmon output directory for DGEA. | [functions README](functions/README.md#get_dgea_salmon_dir) |
| [`get_dgea_samplesheet`](functions/get_dgea_samplesheet.py) | Resolve the upstream samplesheet used for DGEA metadata. | [functions README](functions/README.md#get_dgea_samplesheet) |
| [`get_dgea_organism`](functions/get_dgea_organism.py) | Convert upstream genome or organism metadata into a DGEA organism value. | [functions README](functions/README.md#get_dgea_organism) |
| [`get_dgea_application`](functions/get_dgea_application.py) | Record the upstream application label for DGEA reports. | [functions README](functions/README.md#get_dgea_application) |
| [`get_dgea_name`](functions/get_dgea_name.py) | Use the active Linkar project name as the DGEA report name. | [functions README](functions/README.md#get_dgea_name) |
| [`get_dgea_authors`](functions/get_dgea_authors.py) | Read project author metadata for DGEA reports. | [functions README](functions/README.md#get_dgea_authors) |
| [`software_versions`](functions/software_versions.py) | Write standardized `software_versions.json` files for methods generation. | [functions README](functions/README.md#software_versions) |

Internal helper modules are documented in the functions README but are not intended to be called directly from `linkar_pack.yaml`.

## Discovery Helpers

The `discovery/` modules are read-only helpers for agents and automation layers. They do not execute templates. They help answer questions such as:

- Which project folders exist under a configured project root?
- Which raw or processed sequencing runs are available?
- Which references look relevant for a workflow?

Example:

```python
from discovery.projects import list_projects
from discovery.references import recommended_references

projects = list_projects("/data/projects")
references = recommended_references(organism="example_organism", workflow="example_workflow")
```

## Development Checks

Run focused template tests:

```bash
python3 templates/cellranger_atac/test.py
python3 templates/methods/test.py
python3 templates/dgea/test.py
python3 templates/nfcore_3mrnaseq/test.py
```

Run discovery tests:

```bash
python3 -m unittest discovery.test_discovery
```

Validate YAML syntax after editing templates:

```bash
python3 - <<'PY'
from pathlib import Path
import yaml

for path in Path("templates").glob("*/linkar_template.yaml"):
    yaml.safe_load(path.read_text())
    print("ok", path)
PY
```
