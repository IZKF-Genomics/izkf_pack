# methylation_array_analysis

This template creates one editable Illumina methylation array study workspace for a Linkar project.

The Linkar project is treated as the study. The workspace derives the report project name from the
Linkar project directory and does not expose a separate `study_name` parameter.

Only `pixi` and `python3` are required on the host system. `quarto`, `Rscript`, and the R/Bioconductor
stack are installed inside the template-local Pixi environment.

## Workspace Model

The template is centered around:

- [DNAm_constructor.R](DNAm_constructor.R)
- `config/datasets.toml`
- `config/samples.csv`

The normal user flow is:

1. render the workspace
2. register or fetch datasets
3. sync sample metadata
4. edit `samples.csv`
5. define comparisons directly in `DNAm_constructor.R`
6. run the analysis

## Quick Start

Render the workspace into your Linkar project:

```bash
linkar render methylation_array_analysis --pack /path/to/izkf_pack
cd methylation_array_analysis
```

Then use this sequence:

```bash
pixi install
pixi run sync-samples
pixi run preflight
```

Edit:

- `config/datasets.toml`
- `config/samples.csv`
- [DNAm_constructor.R](DNAm_constructor.R)

Run the full study:

```bash
./run.sh
```

## Data Ingestion

Supported input patterns:

- local or shared IDAT folders registered with `pixi run register-local --dataset-id ... --path ...`
- GEO supplementary downloads through `pixi run fetch-geo --accession GSE...`
- manual inbox folders under `data/inbox/<dataset_id>/`

### Option 1: Register A Local Or Shared IDAT Folder

Use this when your IDAT files already exist somewhere on disk and you do not want to move them into the workspace.

```bash
pixi run register-local --dataset-id batch1 --path /path/to/idat_folder --array-type EPIC_V2
pixi run sync-samples
pixi run preflight
```

This adds or updates the dataset entry in `config/datasets.toml` and regenerates `config/samples.csv`.

### Option 2: Download GEO Supplementary Files

Use this when the GEO series has raw IDATs or archives containing IDATs.

```bash
pixi run fetch-geo --accession GSE123456
pixi run sync-samples
pixi run preflight
```

The files are downloaded under `data/geo/<dataset_id>/` and the dataset is registered in `config/datasets.toml`.

### Option 3: Copy Or Link Data Into The Workspace Inbox

Use this when you want a simple manual workflow.

1. Create a folder such as `data/inbox/my_batch/`
2. Copy or link the IDAT pairs into that folder
3. Add or edit the matching dataset block in `config/datasets.toml`

Example dataset block:

```toml
[[datasets]]
dataset_id = "my_batch"
source = "inbox"
path = "data/inbox/my_batch"
array_type = "EPIC_V2"
enabled = true
```

Then regenerate the sample table:

```bash
pixi run sync-samples
pixi run preflight
```

After registering or downloading data, regenerate the sample table:

```bash
pixi run sync-samples
pixi run preflight
```

`sync-samples` preserves existing editable annotations in `config/samples.csv` when possible.

## Edit The Sample Table

The auto-generated [config/samples.csv](config/samples.csv) is the main place to curate the cohort.

Typical edits:

- set `group`
- set `subgroup`
- set `batch`
- set `analysis_set`
- set `include=false` to remove bad samples
- fill `exclude_reason`
- add clinical columns such as `sex` and `age`

Important columns:

- `sample_id`: must stay unique
- `dataset_id`: links the sample back to the dataset registry
- `group`: used for comparisons
- `include`: controls whether the sample enters the analysis
- `SentrixBarcode` / `SentrixPosition`: used when deriving IDAT basenames from array positions
- `idat_dir` / `idat_basename`: optional manual overrides for raw data resolution

If you make dataset-level changes later, run `pixi run sync-samples` again. Existing editable columns are preserved when possible.

## Define Comparisons In The Constructor

Comparisons are defined directly in [DNAm_constructor.R](DNAm_constructor.R), not in a CSV.

The constructor builds:

- one global study configuration
- one list of comparison configurations

Each comparison can override:

- `samples`
- `target_group`
- `base_group`
- `covariates`
- `delta_beta_min`
- `use_batch_corrected`
- `dmr_enabled`
- `enrichment_enabled`
- `drilldown`

Example:

```r
comparisons <- list(
  list(
    name = "Tumor_vs_Control_main",
    samples = dplyr::filter(samples, analysis_set == "main", include == TRUE),
    target_group = "Tumor",
    base_group = "Control",
    covariates = c("age", "sex"),
    delta_beta_min = 0.15,
    use_batch_corrected = TRUE,
    dmr_enabled = TRUE,
    enrichment_enabled = TRUE,
    drilldown = list(
      genes = c("BRCA1", "NF1"),
      loci = c("chr17:43044295-43125482")
    )
  ),
  list(
    name = "Tumor_subgroupA_vs_Control",
    samples = dplyr::filter(samples, subgroup == "A", include == TRUE),
    target_group = "Tumor",
    base_group = "Control"
  )
)
```

This is the intended place to duplicate comparisons, remove outliers for one contrast only, or tune thresholds per contrast.

## Run The Analysis

For the normal full workflow inside the rendered workspace:

```bash
pixi install
pixi run sync-samples
pixi run preflight
./run.sh
```

`./run.sh` does not regenerate `config/samples.csv` by default. This is intentional so manual edits
to `sample_id`, `group`, and other annotations are preserved across reruns.

If you changed the dataset registry or added/removed IDAT files and want to rebuild the sample table,
run:

```bash
pixi run sync-samples
pixi run preflight
./run.sh
```

Or force it in one command:

```bash
DNAM_FORCE_SYNC=1 ./run.sh
```

If you only changed the constructor or sample metadata and want to rerun the study:

```bash
./run.sh
```

If preprocessing already succeeded and you only want to rerun failed comparison reports from the
cached merged object in `results/rds/combined_active.rds`, use:

```bash
pixi run Rscript rerun_failed_comparisons.R --from 3
```

Or rerun only selected report orders:

```bash
pixi run Rscript rerun_failed_comparisons.R --only 3,4,7
```

This does not rerun global reports or raw preprocessing. It only recomputes the selected comparison
analyses and renders their standalone HTML reports.

If you only changed data registration and need to rebuild the sample table first:

```bash
pixi run sync-samples
pixi run preflight
./run.sh
```

## Run

Inside a rendered workspace:

```bash
./run.sh
```

Or directly through Linkar:

```bash
linkar run methylation_array_analysis --pack /path/to/izkf_pack
```

## Outputs

Ordered reports are written to `reports/`:

- `00_study_overview.html`
- `01_input_qc.html`
- `02_all_samples_embeddings.html`
- `03_<ComparisonLabel>.html`
- `04_<ComparisonLabel>.html`
- additional comparison reports follow the constructor order

Intermediate objects, tables, and figures are written under `results/`.

The comparison reports are standalone. Each one includes:

- comparison definition
- sample manifest
- DMP results
- DMR results
- enrichment analysis
- drilldown outputs for that comparison
