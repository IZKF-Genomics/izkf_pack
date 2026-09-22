# mirna_differential

This render-mode Linkar template creates an editable DESeq2 workspace for raw mature-miRNA counts from `nf-core/smrnaseq`. It supports ordinary two-group, paired-time, and nested-subject group-by-time interaction analyses.

The default report is deliberately one substantial document rather than a collection of sparse pages. It combines study design, input provenance, filtering, sample QC, global structure, paired trajectories, the primary interaction, secondary contrasts, cross-contrast agreement, interpretation, limitations, methods, and reproducibility details.

## Linkar interface

With the default binding, Linkar resolves:

- `counts_file` from `edger_qc_dir/mature_counts.csv` of the latest `nfcore_smrnaseq` run
- `hairpin_counts_file` from the matching optional `hairpin_counts.csv`
- `samplesheet` from the upstream rendered samplesheet
- `organism` from the upstream genome
- `name` and `authors` from project metadata

Important outputs include:

- `reports/miRNA_differential_report.html` — concise biological overview
- `reports/comparisons/*.html` — one focused report per configured comparison
- `results/tables/miRNA_differential_results.xlsx`
- one complete CSV for every contrast
- PNG, PDF, and SVG versions of all figures
- `results/run_info.yaml`, `results/runtime_command.json`, and `results/software_versions.json`

## Workflow

Render the editable workspace:

```bash
linkar render mirna_differential --binding default
```

Configure sample metadata and models:

```bash
./run.sh --configure
```

The configurator hides sequencing-only columns, parses names ending in `_<time>_<subject>`, previews the resulting group/time/subject table, and writes ordinary files:

- `config/samples.csv`
- `config/analysis.yaml`

Validate before running:

```bash
./run.sh --validate
```

Validation checks count orientation and integer values, exact sample matching, unique contrast ids, required factor levels, and complete subject pairs. R performs an additional full-rank model-matrix check.

Run the analysis after reviewing the configuration:

```bash
./run.sh
```

If configuration files are absent and sample names are unambiguous, the normal run creates a conservative two-group/two-time default and validates it before installing the Pixi environment. Existing configuration is never silently overwritten.

## Statistical direction

For a longitudinal interaction, positive log2 fold change means:

```text
(target group: target time - base time)
-
(base group: target time - base time) > 0
```

The paired interaction model is:

```r
~ subject_nested + time + group_time_interaction
```

`subject_nested` is constructed as a safe `group_subject` factor. `group_time_interaction` is one indicator for target-group observations at the target time, so its coefficient is the configured difference-in-differences. A separate group main effect is intentionally omitted because group is fixed within subject and would make the model non-full-rank.

Setting `supplementary.analyze_hairpin: true` runs the same QC and configured contrasts on `hairpin_counts.csv` in an independent `results/hairpin` tree. Mature and hairpin counts are never pooled, and the report labels hairpin findings as supplementary.

Result tables retain raw DESeq2 log2 fold changes, standard errors, Wald confidence intervals, p values, and FDR. Normal-prior shrunken log2 fold changes are stored separately and used for ranking and visualizations.

## Report completeness

Each enabled contrast must produce a non-empty result table plus MA, volcano, forest, and heatmap figures. The report explains the question, direction, model, evidence, effect uncertainty, and limitations even when no miRNA reaches FDR. Runtime checks reject missing or empty assets and an unexpectedly small HTML report.

## Test commands

```bash
cd templates/mirna_differential
python3 test.py
```

For a real-data run, render the template in a project with a completed `nfcore_smrnaseq` workspace, review the generated configuration, validate, and then run it. The first Pixi solve/install may require network access.
