# IZKF Genomics Pack

`izkf_genomics_pack` is a Linkar pack for genomics-oriented templates.

It keeps each template self-contained while still providing a pack-level default binding for common chaining.

## Layout

```text
izkf_genomics_pack/
  linkar_pack.yaml
  templates/
    demultiplex/
      linkar_template.yaml
      run.py
      test.py
      README.md
    fastqc/
      linkar_template.yaml
      run.sh
      test.sh
      README.md
    multiqc/
      linkar_template.yaml
      run.sh
      test.sh
      README.md
  functions/
  discovery/
```

## Templates

### `demultiplex`

Runs the bundled demultiplexing pipeline in either `demux` or `qc` mode and records stage outputs under `results/`.

Test commands:

```bash
cd /Users/jovesus/github/izkf_genomics_pack/templates/demultiplex
python test.py
```

```bash
pixi run linkar test demultiplex --pack /Users/jovesus/github/izkf_genomics_pack
```

### `fastqc`

A minimal shell-based template that writes placeholder FastQC outputs under `results/fastqc`.

Test commands:

```bash
cd /Users/jovesus/github/izkf_genomics_pack/templates/fastqc
bash test.sh
```

```bash
pixi run linkar test fastqc --pack /Users/jovesus/github/izkf_genomics_pack
```

### `multiqc`

A minimal shell-based template that writes placeholder MultiQC outputs under `results/multiqc`.

The pack-level default binding in `linkar_pack.yaml` lets `multiqc` reuse the latest `demultiplex.results_dir` in project mode.

Test commands:

```bash
cd /Users/jovesus/github/izkf_genomics_pack/templates/multiqc
bash test.sh
```

```bash
pixi run linkar test multiqc --pack /Users/jovesus/github/izkf_genomics_pack
```

## Example Use

Ad hoc:

```bash
linkar run fastqc --pack /Users/jovesus/github/izkf_genomics_pack --param input=/data/sample.fastq.gz
```

Project mode:

```bash
mkdir study && cd study
linkar project init --name study
linkar pack add /Users/jovesus/github/izkf_genomics_pack --id izkf --binding default
```

Then run:

```bash
linkar run demultiplex --mode qc --in-fastq-dir /data/fastq
linkar run multiqc
```

## Site discovery helpers

This pack can also hold site-specific discovery logic without pushing facility knowledge into
Linkar core.

The first discovery modules now live under `discovery/`:

- `discovery/projects.py`
- `discovery/fastq_runs.py`
- `discovery/raw_runs.py`
- `discovery/references.py`

These helpers are intentionally read-only and summary-oriented. They are meant to help an AI agent
or another automation layer find likely projects, FASTQ runs, raw runs, or references before using
Linkar itself to resolve and execute templates.

Example:

```python
from discovery.projects import list_projects
from discovery.fastq_runs import recent_fastq_runs
from discovery.references import recommended_references

projects = list_projects("/data/projects")
fastq_runs = recent_fastq_runs(roots="/data/fastq")
refs = recommended_references(organism="GRCm39", workflow="arc")
```

Run the pack-side unit tests with:

```bash
cd /home/ckuo/github/izkf_pack
python -m unittest discovery.test_discovery
```
