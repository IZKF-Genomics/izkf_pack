# export_demux

Direct-run template for exporting an ad hoc demultiplex run.

Unlike the main `export` template, this action is meant for demultiplex runs that were rendered and executed without a Linkar project. The canonical export metadata is stored under the source run directory:

```text
<run_dir>/.linkar/export_demux/latest/
```

That avoids ambiguity about where export state lives when the action is triggered outside a project.

## Defaults

If not overridden, the template expects:

- FASTQ directory: `output_dir` from `<run_dir>/.linkar/meta.json`, the common parent of `demux_fastq_files`, then `<run_dir>/results/output`, then `<run_dir>/output`
- MultiQC report: `multiqc_report` from `<run_dir>/.linkar/meta.json`, then `<run_dir>/results/multiqc/multiqc_report.html`, then `<run_dir>/multiqc/multiqc_report.html`

Optional overrides include `project_name`, `author`, `fastq_dir`, and `multiqc_report`.

For a demultiplex run with multiple `Sample_Project` folders, use `sample_project` to export just
one project. The template then defaults to:

- FASTQ directory: `<run_dir>/results/output/<Sample_Project>`
- MultiQC report: `<run_dir>/results/output/<Sample_Project>/qc/multiqc/multiqc_report.html`
- export destination: `1_Raw_data/<Sample_Project>`

Example:

```bash
linkar run export_demux \
  --run-dir /path/to/processed_runs/example_run \
  --sample-project Project_A \
  --project-name Project_A_fastq_export \
  --verbose
```

## Canonical metadata

After a successful run, these files are written under:

```text
<run_dir>/.linkar/export_demux/latest/
```

- `export_job_spec.json`
- `export_job_spec.redacted.json`
- `export_response.json`
- `export_final_message.json`
- `export_job_id.txt`
- `export_final_path.txt`

The Linkar action run also keeps a lightweight trace in its own `results/`, but the source-side `.linkar/export_demux/latest/` directory is the canonical location.

## Dry run

Use `--dry-run true` to build and persist the redacted export spec without submitting anything.

Example:

```bash
linkar run export_demux \
  --run-dir /data/fastq/20250101_INST_0001_AAAAAAAAXX \
  --author "CKuo, IZKF" \
  --project-name 20250101_Surname_Project_Assay_FASTQ
```
