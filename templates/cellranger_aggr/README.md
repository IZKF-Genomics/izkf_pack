# Cell Ranger aggr

This template combines compatible outputs from multiple Cell Ranger GEM-well
runs. It supports Gene Expression with or without Feature Barcode libraries,
complete `cellranger multi` sample outputs, and V(D)J contig outputs. It keeps
aggregation separate from primary processing so that projects only incur the
additional matrix, Loupe, and secondary-analysis storage when aggregation is
actually useful.

## Quick start

From an initialized Linkar project with collected Cell Ranger outputs:

```bash
linkar render cellranger_aggr --binding default
cd cellranger_aggr
./run.sh --prepare-only
./run.sh
```

The default binding finds the latest compatible Cell Ranger result in the
project, writes its paths to `config/aggregation.csv`, and lets the CSV header
select the correct aggregation mode. No Agendo ID is needed because this
template consumes processed Cell Ranger outputs rather than sequencing booking
metadata.

Always inspect these files before starting the run:

```text
config/aggregation.csv
config/cellranger_aggr.toml
```

`./run.sh --prepare-only` validates the files, creates an absolute-path runtime
CSV, records software versions and the exact command, and does not start Cell
Ranger.

## What the automatic binding does

The binding examines the newest collected `cellranger_multi`,
`cellranger_count`, or `cellranger_vdj` result that exposes an aggregation
input. It does not combine unrelated historical template runs.

For GEX or Feature Barcode results, it uses collected `molecule_info.h5` or
per-sample `sample_molecule_info.h5` files:

```csv
sample_id,molecule_h5
control_rep1,/project/cellranger_multi/results/control/outs/per_sample_outs/control_rep1/sample_molecule_info.h5
control_rep2,/project/cellranger_multi/results/control/outs/per_sample_outs/control_rep2/sample_molecule_info.h5
```

If per-sample outputs contain V(D)J directories, it selects complete multi mode
instead. Because donor identity and biological origin cannot be inferred safely
from a path, the generated CSV contains `__EDIT_ME__` placeholders. Rendering
succeeds, but execution stops until those values are replaced.

Pure V(D)J outputs behave the same way: paths are populated automatically and
`donor`/`origin` require review.

Provide a CSV explicitly when there is no collected upstream result or when a
custom cohort is required:

```bash
linkar render cellranger_aggr \
  --aggregation-csv /path/to/my_aggregation.csv
```

## The three supported CSV schemas

The template infers the mode from exactly one of `molecule_h5`, `sample_outs`,
or `vdj_contig_info`. Do not combine those columns in one CSV.

### Gene Expression with or without Feature Barcode

```csv
sample_id,molecule_h5,condition,replicate
control_1,/runs/control_1/outs/molecule_info.h5,control,1
treated_1,/runs/treated_1/outs/molecule_info.h5,treated,1
```

Use this schema for:

- `cellranger count` GEX outputs;
- per-sample `cellranger multi` GEX outputs;
- GEX plus Antibody Capture, including antibody hashing;
- GEX plus CRISPR Guide Capture;
- other compatible Feature Barcode data stored in the molecule H5.

For multiplexed `cellranger multi`, use each biological sample's
`sample_molecule_info.h5`, not the GEM well's top-level raw molecule file. The
Feature Reference used for the source GEM wells must be consistent.

Any extra CSV columns are carried into Cell Ranger as sample categories and can
be inspected in Loupe Browser. Useful examples are `condition`, `replicate`,
`tissue`, `sex`, and `batch`.

### Complete cellranger multi outputs

```csv
sample_id,sample_outs,donor,origin,condition
sample_1,/runs/run_1/outs/per_sample_outs/sample_1,donor_1,blood_t0,control
sample_2,/runs/run_2/outs/per_sample_outs/sample_2,donor_1,blood_t1,treated
```

Use `sample_outs` when all modalities in a multi run should be aggregated
together. Cell Ranger can auto-detect compatible combinations of 5' GEX,
Antibody Capture, CRISPR Guide Capture, BCR/TCR, and Antigen Capture (BEAM).

Every input must contain the same library combination. For example,
`GEX+BCR+TCR` cannot be combined as complete multi output with `GEX+BCR`. If
only one modality is needed, use the corresponding molecule H5 or V(D)J contig
schema instead.

### V(D)J-only or mixed vdj/multi sources

```csv
sample_id,vdj_contig_info,donor,origin
sample_1,/runs/run_1/outs/vdj_contig_info.pb,donor_1,blood_t0
sample_2,/runs/run_2/outs/per_sample_outs/sample_2/vdj_b/vdj_contig_info.pb,donor_1,blood_t1
```

This schema can mix compatible `cellranger vdj` and `cellranger multi` V(D)J
outputs. All inputs must use compatible V(D)J references and chain types.
TRG/TRD-enriched libraries are not supported by `cellranger aggr`.

For V(D)J aggregation:

- `donor` identifies the biological individual;
- `origin` identifies a source within that donor, such as tissue, condition, or
  time point;
- cells from different donors are not placed in the same clonotype;
- datasets with the same donor and origin are treated as replicates and trigger
  additional artifact filtering.

Do not invent donor/origin values merely to satisfy the CSV. Confirm them from
the experimental design.

## Normalization policy

The rendered `config/cellranger_aggr.toml` defaults to:

```toml
[aggregation]
normalize = "none"
```

This deliberately differs from Cell Ranger's `mapped` default.

- `none` retains all reads and is the conservative choice when Scanpy, Seurat,
  scVI, or another downstream workflow will perform normalization and
  integration.
- `mapped` downsamples each library type to comparable mapped/assigned reads per
  cell. It can be useful for a directly depth-balanced Cell Ranger/Loupe view,
  but discarded reads cannot be recovered from the aggregated matrix.

Change the setting explicitly if mapped-depth normalization is intended:

```toml
[aggregation]
normalize = "mapped"
```

For different GEX chemistry generations, Cell Ranger supports a `batch` column:

```csv
sample_id,molecule_h5,batch
sample_v2,/runs/sample_v2/outs/molecule_info.h5,chemistry_v2
sample_v3,/runs/sample_v3/outs/molecule_info.h5,chemistry_v3
```

This is chemistry batch correction. It is not a replacement for biological
batch assessment or downstream integration.

## Runtime settings

The editable settings file is `config/cellranger_aggr.toml`:

```toml
[run]
id = "aggregated"

[aggregation]
normalize = "none"

[analysis]
nosecondary = false
enable_tsne = false
min_crispr_umi = 3

[runtime]
cellranger_bin = "/data/shared/10xGenomics/bin/cellranger-10.0.0/bin/cellranger"
localcores = 16
localmem = 64
```

`localcores = 0` lets Cell Ranger choose unless the default Linkar binding has
filled the host CPU limit. Cell Ranger recommends at least 64 GB RAM for up to
250,000 cells, with more memory required for larger datasets.

The template writes normalized absolute input paths to
`generated/aggregation.csv`. Do not edit that generated file; edit
`config/aggregation.csv` and rerun instead.

## Preflight and CLI messages

Run:

```bash
./run.sh --prepare-only
```

The preflight checks:

- that there are at least two inputs;
- the CSV uses exactly one supported schema;
- sample IDs and input paths are unique;
- every input path exists and has the expected file/directory type;
- donor/origin values are present for multi and V(D)J modes;
- no generated placeholder remains;
- complete multi inputs have consistent detectable library combinations;
- known V(D)J chain directories are compatible;
- normalization, run ID, cores, memory, and analysis settings are valid;
- the Cell Ranger executable is available.

It then prints the detected mode, input count, normalization choice, Cell
Ranger version, and exact command. Errors name the affected file and usually
include the next corrective action.

## When not to use aggr

Do not use `cellranger aggr` to combine resequencing runs of the same library.
Supply all FASTQs from that library to one original `cellranger count` or
`cellranger multi` run.

Aggregation creates a union matrix and common secondary analyses; it does not
make distinct biological samples equivalent and is not, by itself, a general
batch-integration method. Depending on the scientific question, it can be
preferable to load the individual matrices directly into a downstream workflow
and concatenate them there.

Starting with Cell Ranger 8, `aggr` does not support Targeted Gene Expression
or LT libraries. Verify new assay combinations against the documentation for
the installed Cell Ranger version rather than assuming that every assay handled
by `count` or `multi` can be aggregated.

## Outputs and Linkar collection

Cell Ranger writes the pipestance under:

```text
results/<run.id>/outs/
```

The template records the following in the template entry in `project.yaml`
without copying them:

- all Cell Ranger HTML reports;
- `summary.json` and metric CSV files;
- filtered H5 and MEX feature-barcode matrices;
- Loupe `.cloupe` and V(D)J `.vloupe` files;
- general, antibody, and CRISPR analysis directories;
- clonotype, contig annotation, AIRR, consensus, and donor-region outputs;
- the reviewed and runtime aggregation CSV files;
- the exact runtime command and software versions.

After a successful normal run, `run.sh` calls `linkar collect` when it detects a
rendered Linkar workspace. If collection was skipped, run:

```bash
linkar collect cellranger_aggr
```

The first QC file to review is `web_summary.html`. For normalized runs, inspect
the fraction of reads retained per input in `summary.json` or the web summary.

`cellranger aggr` does not reproduce the large input BAM and molecule H5 files,
and recent versions do not emit a raw feature-barcode matrix. It still creates
a new filtered matrix, Loupe file, and secondary analyses, so the template keeps
aggregation opt-in and separate from primary processing.

## Examples supplied with the template

The `examples/` directory contains editable references for:

- `aggregation_molecule_h5.csv`;
- `aggregation_multi.csv`;
- `aggregation_vdj.csv`;
- `aggregation_batch.csv`.

These contain placeholder paths for documentation only. A normal render with
`--binding default` writes real project paths into `config/aggregation.csv`.

## Official references

- [Aggregating multiple samples with Cell Ranger aggr](https://www.10xgenomics.com/support/software/cell-ranger/10.0/analysis/running-pipelines/cr-3p-aggr)
- [Cell Ranger command-line arguments](https://www.10xgenomics.com/support/software/cell-ranger/latest/resources/cr-command-line-arguments)
- [Cell Ranger aggr outputs](https://www.10xgenomics.com/support/software/cell-ranger/latest/tutorials/outputs/cr-outputs-aggr-outputs)
- [Cell Ranger aggr summary metrics](https://www.10xgenomics.com/support/software/cell-ranger/10.0/analysis/outputs/cr-outputs-metrics-aggr)
- [Cell Ranger Feature Reference CSV](https://www.10xgenomics.com/support/software/cell-ranger/10.0/analysis/inputs/cr-feature-ref-csv)
- [Single-cell best practices](https://www.sc-best-practices.org/preamble.html)
