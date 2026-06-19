# dgea

This template provides a clean DGEA workspace for Linkar projects.

It keeps the analyst-facing workflow in R/Quarto:

- editable [DGEA_constructor.R](DGEA_constructor.R)
- bundled Quarto reports
- bundled [pixi.toml](pixi.toml) and [pixi.lock](pixi.lock)
- bundled Positron settings in [.vscode/settings.json](.vscode/settings.json)

The template only requires `pixi` on the host. `quarto` and `Rscript` are provided by the template-local Pixi environment.

Instead of BPM Jinja rendering, Linkar now writes a small `dgea_inputs.R` file through [build_dgea_inputs.py](build_dgea_inputs.py). The constructor stays editable and programmable.

## Runtime model

`linkar render dgea`:

- stages an editable analyst workspace
- writes rendered `.vscode/settings.json` paths for the local workspace automatically
- does not execute the analysis

`linkar run dgea`:

- runs the standalone [run.sh](run.sh)
- writes `dgea_inputs.R`
- installs the Pixi environment from the lockfile with bounded retries and a timeout
- runs `install_bioc_data.sh` once per Pixi environment
- executes `DGEA_constructor.R`
- records `software_versions.json`

`./run.sh --configure`:

- writes `dgea_inputs.R`
- opens an interactive terminal configurator through the template Pixi environment
- shows an analysis-facing sample table while hiding nf-core sequencing columns such as `fastq_1`, `fastq_2`, and `strandedness`
- can derive metadata from underscore-separated sample names such as `KO_Basal_Treat1_1`
- writes ordinary R code into marked blocks in [DGEA_constructor.R](DGEA_constructor.R)
- stops after writing so you can inspect or edit the constructor before running `./run.sh`

## Bindings

With `--binding default`, the pack resolves:

- `salmon_dir` from the latest upstream nf-core outputs
- `samplesheet` from the latest upstream nf-core params
- `organism` from upstream genome or organism
- `application` from the latest upstream template id
- `name` from the project name
- `authors` from project author metadata

## Editing

The main control surface is [DGEA_constructor.R](DGEA_constructor.R).

The rendered constructor:

- always renders the all-samples overview
- keeps sample metadata and comparisons in marked editable blocks
- expects pairwise reports to be configured with `./run.sh --configure` or by editing the `comparisons` list manually
- uses `design_formula` as the transparent DESeq2 model control; paired or repeated designs should be written as formulas such as `~ id + group`

That keeps the workflow flexible for:

- many pairwise comparisons
- selective sample exclusion
- relabeling groups
- changing design formulas
- enabling or disabling optional reports

## Interactive comparison configuration

Run:

```bash
./run.sh --configure
```

The configurator first prints the detected samples. Technical nf-core input columns are hidden from the display but remain available in the original samplesheet.

Terminal output uses `rich` from the Pixi environment for tables, panels, prompts, warnings, validation messages, and syntax-highlighted R-code previews. Set `NO_COLOR=1` to disable color while keeping the structured layout.

If no `group` column is present, the configurator can split `sample` by underscores and ask you to name each part. For example, `KO_Basal_Treat1_1` can become:

```text
genotype = KO
condition = Basal
treatment = Treat1
id = 1
group = KO_Basal_Treat1
```

For each comparison, choose `Add comparison` or finish. Each comparison can use all samples or a subset, choose its own base group, target group, design formula, and GO/GSEA settings. Before writing, the exact R code is previewed.

The generated code is placed between:

```r
# BEGIN CONFIGURED SAMPLE METADATA
# END CONFIGURED SAMPLE METADATA

# BEGIN CONFIGURED COMPARISONS
# END CONFIGURED COMPARISONS
```

Only those blocks are replaced by the configurator.

## Test commands

```bash
cd templates/dgea
python3 test.py
```

## Pixi install troubleshooting

The first run may need to download many conda packages from the locked channels in
[pixi.lock](pixi.lock). It also downloads Bioconductor annotation data packages after the Pixi
environment is installed. These steps use bounded retries and timeouts instead of waiting
indefinitely when a mirror stops responding. The defaults are:

```bash
LINKAR_PIXI_INSTALL_TIMEOUT_SECONDS=1800
LINKAR_PIXI_INSTALL_RETRIES=2
LINKAR_PIXI_CONCURRENT_DOWNLOADS=8
LINKAR_BIOC_DATA_TIMEOUT_SECONDS=900
LINKAR_BIOC_DATA_RETRIES=2
```

Override these only when the network or mirror is unusually slow, for example:

```bash
LINKAR_PIXI_INSTALL_TIMEOUT_SECONDS=3600 LINKAR_BIOC_DATA_TIMEOUT_SECONDS=1800 ./run.sh
```

Bioconductor data downloads are selected from the requested `organism` instead of installing every
bundled organism package. The template always installs shared `genomeinfodbdata` and `go.db` data,
then adds one organism-specific package when available:

- `hsapiens`: `org.hs.eg.db`
- `mmusculus`: `org.mm.eg.db`
- `sscrofa`: `org.ss.eg.db`

Each data package is stamped independently inside the Pixi environment, so already-installed
packages are skipped on later runs.
