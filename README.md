# Linkar Genomics Pack

This repository is a Linkar pack for routine sequencing data operations. It keeps reusable workflow templates, site-specific binding functions, and read-only discovery helpers in one place so a project can be assembled from small, inspectable steps.

The pack is intentionally practical:

- `templates/` contains runnable Linkar templates.
- `functions/` contains binding functions that resolve parameters from project history, host resources, metadata APIs, or generated helper files.
- `discovery/` contains read-only helpers for finding projects, sequencing runs, references, and processed run folders.
- `linkar_pack.yaml` wires selected templates to default binding functions.

This pack assumes facility-managed shared references and 10x assets are prepared outside the pack itself. Those shared assets are maintained in the companion repository [`genomics-assets`](https://github.com/IZKF-Genomics/genomics-assets).

## Start Here

If you are new to the pack, the usual path is:

1. install the pack
2. configure your user defaults
3. run one of the common workflows below
4. open the relevant template README for template-specific details
5. use the docs folder when you want pack-wide design notes

## How To Read This Repository

Use the documentation in three layers:

- This page: quick setup, common workflows, and the main navigation for the pack.
- `templates/*/README.md`: template-specific usage, parameters, and outputs.
- [`docs/`](docs/README.md): pack-wide conventions and design notes that span multiple templates.

Start here if you want to run the pack. Use the docs folder if you want to
understand why the pack is structured the way it is.

## Deeper Docs

General pack docs:

- [docs/README.md](docs/README.md): index of pack-wide guides
- [docs/software_versions.md](docs/software_versions.md): how template specs become generated `software_versions.json`
- [docs/methods.md](docs/methods.md): how long/short methods outputs are built
- [docs/export.md](docs/export.md): export mapping behavior and `export_job_spec.json`
- [docs/nfcore_templates.md](docs/nfcore_templates.md): shared nf-core launcher and provenance patterns
- [docs/project_history_and_archive.md](docs/project_history_and_archive.md): visible workspaces, `.linkar/runs`, prune, and archive behavior
- [docs/template_outputs.md](docs/template_outputs.md): common runtime artifacts across templates
- [docs/facility_defaults.md](docs/facility_defaults.md): facility-specific assumptions used across templates
- [docs/scverse_scrna_prep.md](docs/scverse_scrna_prep.md): scRNA workspace notes beyond the template README
- [docs/scverse_scrna_integrate.md](docs/scverse_scrna_integrate.md): integration-specific assumptions for the scRNA integration workspace

Template-specific READMEs stay inside each template directory and are listed in
the [Template Catalog](#template-catalog) below.

Template authors and AI agents should also read [TEMPLATE_AUTHORING_FOR_AGENTS.md](TEMPLATE_AUTHORING_FOR_AGENTS.md) before adding a new template. For the general Linkar-side guidance on `run.command`, `run.sh`, `run.py`, and runtime metadata patterns, see the Linkar tutorial `python-entry-and-runtime-metadata.md` in the Linkar docs site.

## Install

Clone the pack and register it as a global Linkar pack:

```bash
cd ~/github/
gh repo clone IZKF-Genomics/izkf_pack
linkar config pack add ~/github/izkf_pack/
```

After this, Linkar can find the pack without passing `--pack` each time.

Check the active global pack:

```bash
linkar config pack show
```

## Configure User Defaults

Configure author metadata once per user. New projects will copy these values into `project.yaml`.

```bash
linkar config author set \
  --name "Example User" \
  --email "user@example.org" \
  --organization "Example Genomics Facility"
```

Check the configured author:

```bash
linkar config author show
```

You can still override author metadata per project:

```bash
linkar project init \
  --name example_project \
  --author-name "Another User" \
  --author-email "another.user@example.org"
```

## Common Workflows

### Run Demultiplexing

Use this when starting from a raw sequencing run folder.

Inspect first, then execute manually:

```bash
cd /path/to/processed_runs/

linkar render demultiplex \
  --bcl-dir /path/to/raw_runs/example_run \
  --agendo-id EXAMPLE_REQUEST_ID

cd example_run
bash run.sh
cd ..
linkar collect example_run
```

One-shot execution:

```bash
cd /path/to/processed_runs/

linkar run demultiplex \
  --bcl-dir /path/to/raw_runs/example_run \
  --agendo-id EXAMPLE_REQUEST_ID \
  --verbose
```

`linkar run` includes render, execution, output collection, and `.linkar` metadata writing in one command. When it runs inside an active Linkar project, it also records the run in `project.yaml`.

Export an ad hoc demultiplexing run:

```bash
linkar run export_demux \
  --run-dir /path/to/processed_runs/example_run \
  --project-name example_fastq_export \
  --verbose
```

### Run nf-core RNA-seq Processing for 3' mRNA-seq

After finishing demultiplexing, create a project and adopt the processed run:

```bash
cd /path/to/projects/

linkar project init \
  --name example_3mrnaseq_project \
  --adopt /path/to/processed_runs/example_run

cd example_3mrnaseq_project
linkar project view
```

Run the nf-core 3' mRNA-seq workflow. The default binding can reuse demultiplex outputs and resolve metadata from `agendo_id`.

```bash
linkar run nfcore_3mrnaseq \
  --agendo-id EXAMPLE_REQUEST_ID \
  --outdir ./nfcore_3mrnaseq \
  --verbose
```

If you want to inspect before execution:

```bash
linkar render nfcore_3mrnaseq \
  --agendo-id EXAMPLE_REQUEST_ID \
  --outdir ./nfcore_3mrnaseq

cd nfcore_3mrnaseq
bash run.sh
cd ..
linkar collect nfcore_3mrnaseq
```

If there are multiple batches in the project and you want to run separate nf-core processing runs, you can do:

```bash
linkar render nfcore_3mrnaseq \
  --agendo-id EXAMPLE_REQUEST_ID \
  --umi true \
  --spikein true \
  --outdir nfcore_tissue1 \
  --genome Sscrofa11.1
```

Don't forget to manually adjust the generated `samplesheet.csv` which by default includes all samples. Then render the template again for another batch with different parameters:

```bash
linkar render nfcore_3mrnaseq \
  --agendo-id EXAMPLE_REQUEST_ID \
  --outdir nfcore_tissue2 \
  --genome Sscrofa11.1
```

### Run Differential Gene Expression Analysis

Run the editable DGEA workspace after RNA-seq quantification outputs are recorded:

```bash
linkar run dgea
```

If there are multiple nf-core runs in the project and you want to use a specific upstream result set:

```bash
linkar render dgea \
  --salmon-dir nfcore_tissue1/results/star_salmon/ \
  --organism sscrofa \
  --application 3mrnaseq \
  --outdir DGEA_Tissue1 \
  --samplesheet nfcore_tissue1/samplesheet.csv
```

### Run ERCC spike-in QC report

Run the ERCC spike-in QC report when the same RNA-seq quantification outputs are available:

```bash
linkar run ercc
```

### RRBS methylation-seq

Run the RRBS-first `nf-core/methylseq` wrapper after demultiplex outputs are recorded:

```bash
linkar run nfcore_methylseq \
  --agendo-id EXAMPLE_REQUEST_ID
```

The default binding can generate the methylseq samplesheet from demultiplexed FASTQ names, resolve `genome`, and set the MultiQC title from the project name.

### Single-cell ATAC-seq

Run Cell Ranger ATAC after a compatible FASTQ directory is recorded or passed explicitly:

```bash
linkar run cellranger_atac \
  --fastq-dir /path/to/processed_runs/example_run/results/output/example_project \
  --reference /path/to/references/example_cellranger_atac_reference
```

### Generate Methods

Use this after one or more analysis runs have been adopted into `project.yaml`. The template now attempts LLM polishing by default and falls back to deterministic drafts if the API settings are missing. Keep secrets in the environment, not in `project.yaml`:

```bash
export LINKAR_LLM_API_KEY="..."
export LINKAR_LLM_BASE_URL="https://api.example.org/v1"
export LINKAR_LLM_MODEL="example-model"

linkar run methods \
  --outdir ./methods \
  --refresh
```

This keeps the visible methods workspace in `./methods` and overwrites `methods/results/` on reruns instead of leaving the user to inspect historical `.linkar/runs/...` snapshots.

### Export

Use this after the project contains the runs and reports you want to publish.

Inspect and edit the generated export specification before submission:

```bash
linkar render export
cd export
less results/export_job_spec.json
bash run.sh
```

One-shot export:

```bash
linkar run export
```

Check an export job:

```bash
linkar run export_status \
  --job-id EXAMPLE_JOB_ID \
  --verbose
```

Delete an export project only when you are certain:

```bash
linkar run export_del \
  --project-id EXAMPLE_EXPORT_PROJECT_ID \
  --confirm-delete true \
  --verbose
```

## Troubleshooting

Show the active project and recorded runs:

```bash
linkar project view
linkar project runs
```

Inspect a run:

```bash
linkar inspect RUN_INSTANCE_ID
```

Collect outputs again after manually executing or editing a rendered run:

```bash
linkar collect ./run_directory
```

Confirm global configuration:

```bash
linkar config pack show
linkar config author show
```

If a required parameter cannot be resolved automatically, pass it explicitly with its template option, for example `--samplesheet`, `--genome`, `--fastq-dir`, or `--reference`.

## Template Catalog

| Template | Purpose | Details |
| --- | --- | --- |
| [`demultiplex`](templates/demultiplex/linkar_template.yaml) | Clone and run the pinned demultiplexing workflow, writing processed outputs under `results/`. | [README](templates/demultiplex/README.md) |
| [`nfcore_3mrnaseq`](templates/nfcore_3mrnaseq/linkar_template.yaml) | Run the site-specific `nf-core/rnaseq` wrapper for 3' mRNA-seq projects. | [README](templates/nfcore_3mrnaseq/README.md) |
| [`scverse_scrna_prep`](templates/scverse_scrna_prep/linkar_template.yaml) | Create and run an editable scverse/Scanpy single-cell RNA-seq preprocessing workspace with Quarto QC reporting. | [README](templates/scverse_scrna_prep/README.md) |
| [`scverse_scrna_integrate`](templates/scverse_scrna_integrate/linkar_template.yaml) | Create and run an editable scverse/Scanpy single-cell RNA-seq dataset integration workspace with baseline and integrated QC reporting. | [README](templates/scverse_scrna_integrate/README.md) |
| [`dgea`](templates/dgea/linkar_template.yaml) | Create and run an editable R/Quarto differential expression workspace. | [README](templates/dgea/README.md) |
| [`ercc`](templates/ercc/linkar_template.yaml) | Create and run an editable ERCC spike-in QC workspace with Quarto reporting. | [README](templates/ercc/README.md) |
| [`methylation_array_analysis`](templates/methylation_array_analysis/linkar_template.yaml) | Create and run an editable Illumina methylation array study workspace with preprocessing, batch-aware analysis, and ordered Quarto reports. | [README](templates/methylation_array_analysis/README.md) |
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

## Functions and Discovery

### Binding Functions

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

### Discovery Helpers

The `discovery/` modules are read-only helpers for agents and automation layers. They do not execute templates. They help answer questions such as:

- Which project folders exist under a configured project root?
- Which raw or processed sequencing runs are available?
- Which references look relevant for a workflow?

Example:

```python
from discovery.projects import list_projects
from discovery.references import recommended_references

projects = list_projects("/path/to/projects")
references = recommended_references(organism="example_organism", workflow="example_workflow")
```

## Development Checks

Run focused template tests:

```bash
python3 templates/cellranger_atac/test.py
python3 templates/methods/test.py
python3 templates/dgea/test.py
python3 templates/nfcore_3mrnaseq/test.py
python3 templates/scverse_scrna_integrate/test.py
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
