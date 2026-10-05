# Cell Ranger multi Linkar template

This template prepares and runs one `cellranger multi` analysis per GEM well.
It is designed for demultiplexed 10x Gene Expression libraries paired with one
Feature Barcode library, including TotalSeq antibody panels and antibody-based
sample hashing. Feature Reference selection and hashtag-to-sample assignments
happen after rendering, so neither a client panel file nor an Agendo ID is
required by `linkar render`.

## Quick start

From an initialized Linkar project containing collected demultiplex FASTQs:

```bash
linkar render cellranger_multi --binding default
cd cellranger_multi
```

The default binding:

- finds libraries whose FASTQ IDs end in `_GEX` and `_FB`;
- pairs them by the shared prefix, for example `WT_ctrl_GEX` + `WT_ctrl_FB`;
- excludes PhiX and unassigned libraries;
- reuses the genome recorded by an earlier project template when available;
- creates one row per GEM well in `config/samples.csv`.

After rendering, configure the Feature Reference and, when applicable, sample
hashing assignments. Validate without starting the analysis:

```bash
./run.sh --prepare-only
```

Then launch all GEM wells sequentially:

```bash
./run.sh
```

Generated inputs are written to `generated/`. Cell Ranger outputs are written
to `results/<gem_well>/`.

After every successful non-prepare run, the template also consolidates the final Cell Ranger
CSV outputs across all GEM wells into:

```text
results/qc/
├── qc_overview.html
├── sample_qc_overview.csv
├── gem_well_library_qc.csv
└── hashtag_assignment_overview.csv
```

- `sample_qc_overview.csv` combines `qc_sample_metrics.csv` into one row per biological sample;
- `gem_well_library_qc.csv` combines the complete long-format `qc_library_metrics.csv` tables;
- `hashtag_assignment_overview.csv` compares singlet, multiplet, unassigned, and no-tag calls;
- `qc_overview.html` provides a cross-sample table, assignment overview, CSV downloads, and links
  back to the original Cell Ranger GEM-well and per-sample reports.

The HTML tables use concise column labels so the overview remains readable on normal screens;
hover over a header to see its complete Cell Ranger metric name. Downloaded CSV files retain the
full, stable column names for analysis and auditability. Numeric cells use tabular monospaced
digits so counts, percentages, and decimal values align for visual comparison.

The collector reports descriptive Cell Ranger primary-analysis metrics and does not impose
universal pass/fail thresholds. For antibody-based hashing, Antibody Capture metrics describe
hashtag signal and must not be interpreted as surface-protein abundance. Cell-level mitochondrial
fraction, count distributions, ambient RNA, and downstream doublet scoring remain part of the
downstream single-cell QC workflow.

For multiplexed experiments, the overview keeps two sequencing-depth concepts separate:

- `GEX: Reads in cells per cell` and `Antibody: Reads in cells per cell` are calculated from the
  reads assigned to each hashtag-defined biological sample;
- `GEM-well GEX total reads`, `GEM-well GEX mean reads per cell`, and
  `GEM-well GEX sequencing saturation` describe the complete pooled GEX library. These values
  repeat for biological samples from the same GEM well and are not independent raw depths for
  each hashed sample.

The source counts (`GEX: Number of reads in cells` and, when available,
`Antibody: Number of reads in cells`) are shown in the HTML table and remain in
`sample_qc_overview.csv` for auditability. These are sample-assigned reads in called cells, not an
independent raw FASTQ read total for each biological sample in a pooled hashing experiment.

To regenerate only the overview after restoring or changing Cell Ranger results:

```bash
python3 collect_qc.py --results-dir ./results
```

## Linkar output contract

`project.yaml` intentionally records only outputs consumed by another template:

- `results_dir` exposes the complete result tree to project-level export and discovery;
- `per_sample_molecule_info` supplies the input files discovered by `cellranger_aggr`;
- `runtime_command` and `software_versions` supply run provenance to `summary`.

QC reports, consolidated QC tables, metrics, matrices, BAM files, indexes, Loupe files, configuration, and generated
multi CSV files remain under the rendered `cellranger_multi/` workspace and are exported from
that filesystem layout. They are deliberately not expanded into large path lists in
`project.yaml` unless a downstream template needs them in the future.

## Mental model: GEM wells, libraries, and biological samples

The three levels are intentionally kept separate:

1. One row in `config/samples.csv` represents one physical GEM well.
2. Its `_GEX` and `_FB` FASTQs become rows in that GEM well's `[libraries]`
   section.
3. For antibody hashing, `config/sample_assignments.csv` describes the
   biological samples pooled inside that GEM well and becomes `[samples]`.

Therefore, four GEM wells containing three hashed biological samples each
produce four `cellranger multi` runs and twelve per-sample outputs. Do not run
`cellranger multi` once per hashtagged biological sample: the GEX and hashtag
reads must be analyzed together at GEM-well level.

## Supported use cases in this template version

| Experiment | Use this template? | Configuration |
| --- | --- | --- |
| GEX + TotalSeq surface-protein panel | Yes | Exact antibody Feature Reference; no assignment rows |
| GEX + TotalSeq antibody hashing | Yes, Cell Ranger 9+ | Exact hashtag Feature Reference plus assignment rows |
| GEX + hashing + surface-protein antibodies in the same FB library | Yes | Put both row types in one Feature Reference; assignments list only hashtag IDs |
| GEX + one CRISPR Guide Capture library | Yes, with manual `samples.csv` editing | Custom guide reference with target columns; set library type to `CRISPR Guide Capture` |
| GEX only | Yes, with manual `samples.csv` editing | Remove the FB values and set `feature.source = "none"` |
| CellPlex/CMO (`Multiplexing Capture`) | Not automated | Requires `cmo_ids`, not `hashtag_ids` |
| On-chip multiplexing (OCM) | Not automated | Requires `ocm_barcode_ids` and chemistry-specific configuration |
| V(D)J, BEAM/Antigen Capture, Flex probe barcodes, or multiple separate FB library types | Not automated | Use a manually authored Cell Ranger multi config until the template gains explicit fields for these layouts |

The runner can validate standard Cell Ranger Feature Reference feature types,
but the automatic binding currently discovers only one `_GEX`/`_FB` pair per
GEM well. Do not relabel an unsupported library type merely to make it fit this
naming convention.

## Choose the Feature Reference

A Feature Reference maps experimental oligo sequences to feature names. It is
not a genome reference. Prefer the exact client/vendor panel whenever it is
available.

### Exact client or vendor file — recommended

Place the file at `config/custom_feature_reference.csv` and configure:

```toml
[feature]
source = "file"
catalog = ""
file = "config/custom_feature_reference.csv"
```

Minimum columns:

```csv
id,name,read,pattern,sequence,feature_type
Hashtag1,Hashtag1_TotalSeqC,R2,5PNNNNNNNNNN(BC),ACCCACCAGTAAGAC,Antibody Capture
```

The runner checks required columns, ASCII-compatible names, barcode sequences,
duplicate IDs, duplicate barcode signatures, feature types, and close barcode
pairs. Cell Ranger remains the final authority on assay compatibility.

### Checked-in broad catalog — fallback only

When the exact panel is unavailable, select one snapshot listed in
`catalogs/manifest.tsv`:

```toml
[feature]
source = "catalog"
catalog = "biolegend_totalseq_c_mouse"
file = ""
```

Catalog IDs cover BioLegend TotalSeq-A, -B, and -C for human and mouse, with
separate antibody and hashing snapshots. A broad catalog is useful for
discovery, but it is not evidence that every listed reagent was used. Unused
barcodes can add background rows and one-mismatch correction can introduce
ambiguity, so replace the broad catalog with the confirmed experimental panel
before final interpretation whenever possible.

The naming scheme is explicit:

```text
biolegend_totalseq_a_human
biolegend_totalseq_a_mouse
biolegend_totalseq_b_human
biolegend_totalseq_b_mouse
biolegend_totalseq_c_human
biolegend_totalseq_c_mouse
```

Append `_hashing` for the corresponding hashtag-only snapshot, for example
`biolegend_totalseq_c_mouse_hashing`. The complete list, source URL, retrieval
date, and row count are recorded in `catalogs/manifest.tsv`.

Temporary overrides are available without editing TOML:

```bash
FEATURE_REFERENCE=/path/to/panel.csv ./run.sh --prepare-only
FEATURE_CATALOG=biolegend_totalseq_c_mouse ./run.sh --prepare-only
```

## Feature Reference decision guide

| Reagent/workflow | Typical chemistry | `read` and `pattern` | `feature_type` | Recommended source |
| --- | --- | --- | --- | --- |
| TotalSeq-A antibody panel | Usually 3′ v2/v3 CITE-seq-style workflows | `R2`, `5P(BC)` or vendor-specified equivalent | `Antibody Capture` | Exact BioLegend/client panel |
| TotalSeq-B antibody panel | 10x 3′ Gene Expression | `R2`, `5PNNNNNNNNNN(BC)` | `Antibody Capture` | Exact BioLegend/client panel |
| TotalSeq-C antibody panel | 10x 5′ Gene Expression | `R2`, `5PNNNNNNNNNN(BC)` | `Antibody Capture` | Exact BioLegend/client panel |
| TotalSeq-A/B/C antibody hashing | Match the TotalSeq family used experimentally | Match that family's vendor pattern | `Antibody Capture` | Exact hashtag products; add `[samples]` assignments |
| PTG antibody panel | Commonly compatible Flex workflows | Usually `R2`, `5P(BC)`; verify the supplied file | `Antibody Capture` | PTG-supplied panel file |
| Custom antibody conjugates | Experiment-specific | From oligo order/conjugation record | `Antibody Capture` | Exact experimental mapping |
| CRISPR guides | 3′/5′/Flex-specific | Assay-specific anchor and orientation | `CRISPR Guide Capture` | Exact guide library with `target_gene_id,target_gene_name` |
| BEAM antigen reagents | Supported 5′ immune profiling combinations | Product/workflow-specific | `Antigen Capture` | Experiment-specific 10x/Immudex reference |
| CellPlex CMO | 10x 3′ Cell Multiplexing | Use 10x CMO definitions | `Multiplexing Capture` | Usually built-in CMO IDs; not this template's hashtag workflow |

Never choose A, B, or C from the species name. Choose it from the reagent
product family and 10x assay chemistry. See `FEATURE_REFERENCES.md` for detailed
column rules and variant notes.

## Configure antibody hashing

For Cell Ranger 9 and later, TotalSeq antibody hashtags remain
`Antibody Capture`. `Multiplexing Capture` is for CellPlex/CMO, not TotalSeq
hashing.

List biological samples in `config/sample_assignments.csv`:

```csv
gem_well,sample_id,hashtag_ids
condition_1,condition_1_rep1,Hashtag1
condition_1,condition_1_rep2,Hashtag2
condition_1,condition_1_rep3,Hashtag3
```

- `gem_well` must match `sample` in `config/samples.csv`.
- `sample_id` is the biological sample name in Cell Ranger outputs.
- `hashtag_ids` must exactly match Feature Reference `id` values.
- Multiple hashtags for one biological sample use a pipe, such as
  `Hashtag1|Hashtag2`.
- A hashtag cannot be assigned to two biological samples in the same GEM well.
- The same hashtag IDs may be reused in independent GEM wells.
- Leave the file with only its header for non-hashed experiments.

Example generated config:

```csv
[gene-expression]
reference,/path/to/refdata-gex-GRCm39-2024-A
create-bam,true

[feature]
reference,/absolute/path/to/generated/feature_reference.csv

[libraries]
fastq_id,fastqs,feature_types
condition_1_GEX,/path/to/fastqs,Gene Expression
condition_1_FB,/path/to/fastqs,Antibody Capture

[samples]
sample_id,hashtag_ids
condition_1_rep1,Hashtag1
condition_1_rep2,Hashtag2
condition_1_rep3,Hashtag3
```

## Runtime settings

`config/cellranger_multi.toml` controls the transcriptome, `create-bam`, Cell
Ranger executable, CPUs, and memory. Cell Ranger 10 requires `create-bam` to be
explicit. The facility default is `true`; set it to `false` before running if
aligned BAM files are not needed and storage should be minimized.

`./run.sh --prepare-only` performs template validation, resolves the Feature
Reference, creates all multi configs, records commands and software versions,
and does not launch Cell Ranger. For the strongest preflight, run Cell Ranger's
own parser against a generated config:

```bash
cellranger multi --dry \
  --id=dry_example \
  --csv="$(pwd)/generated/multi/condition_1.csv"
```

## Outputs and Linkar collection

After all runs finish, `run.sh` calls `linkar collect` when it detects Linkar
metadata. The template declares GEM-level QC reports, all per-sample web
summaries, metrics tables, tag-assignment tables, H5 matrices, molecule files,
Loupe files, BAMs and indexes, generated configs, runtime commands, and software
versions. These paths are written to the template's `outputs` entry in
`project.yaml` rather than copying the large files.

If collection was skipped because `linkar` was unavailable on `PATH`, run:

```bash
linkar collect cellranger_multi
```

The first QC targets for hashing are each GEM well's `qc_report.html`, each
biological sample's `web_summary.html`, and the files under
`outs/multiplexing_analysis/`, especially `tag_calls_summary.csv` and
`assignment_confidence_table.csv`.

## Aggregation is deliberately separate

This template stops after primary `cellranger multi` processing. It does not
run or manage `cellranger aggr`, because aggregation creates another large set
of matrices, Loupe files, and secondary-analysis outputs and is not required by
every downstream workflow. A separate `cellranger_aggr` Linkar template should
own its input selection, normalization policy, storage, outputs, and provenance.

Do not use aggregation to combine resequencing runs of the same library. Those
FASTQs belong in the original GEM well's `cellranger multi` input.

## Official references

- [Cell Ranger multi overview and supported assays](https://www.10xgenomics.com/support/software/cell-ranger/10.0/analysis/running-pipelines/cr-multi)
- [Cell Ranger multi config CSV options](https://www.10xgenomics.com/support/software/cell-ranger/10.0/analysis/inputs/cr-multi-config-csv-opts)
- [Feature Reference CSV specification and examples](https://www.10xgenomics.com/support/software/cell-ranger/latest/tutorials/inputs/cr-feature-ref-csv)
- [BioLegend TotalSeq barcode lookup](https://www.biolegend.com/en-us/totalseq/barcode-lookup)
- [3′/5′ multiplexing examples, including antibody hashing](https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/cr-3p-multi)
- [Multiplexed `cellranger multi` output structure](https://www.10xgenomics.com/support/software/cell-ranger/10.0/analysis/outputs/cr-3p-outputs-cellplex)
- [Single-cell best practices](https://www.sc-best-practices.org/preamble.html)

Vendor catalogs and product pages are helpful for barcode lookup, but the
client's reagent record remains the authoritative source for the panel actually
used.
