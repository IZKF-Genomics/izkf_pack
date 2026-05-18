# scrna_annotate

Status: design-only scaffold. Provider execution code has intentionally not been generated yet.

This directory defines the planned architecture for a provider-based single-cell RNA-seq
annotation runner. The old tiered implementation has been removed so the next implementation can
start from a clean contract.

The core idea:

- `scrna_annotate` executes independent annotation providers.
- Each provider owns its own folder, manifest, environment, and execution script.
- Each provider writes one standard `annotation_result.json`, even when it is skipped or fails.
- Each provider may write a method-level Quarto report for human review.
- `scrna_audit` will read those JSON files and produce comparison, visualization, consensus, and
  benchmark/review reports that link back to method-level reports.

This follows the single-cell best-practices view that cell type annotation should expose evidence,
uncertainty, and reviewable assumptions rather than acting as a one-click source of truth.

Reference guidance:

- <https://www.sc-best-practices.org/cellular_structure/annotation.html>

## Boundary

`scrna_annotate` is responsible for execution.

It should:

- inspect the input `.h5ad`
- write `results/dataset_profile.json`
- read provider manifests
- validate provider readiness
- run enabled providers
- write provider status and provider outputs
- write provider-level Quarto reports when the provider supports them

It should not:

- decide the final biological label
- hide provider failures
- silently guess tissue-specific references
- run every method by default
- compare provider results beyond minimal indexing
- make HTML rendering mandatory for successful annotation

`scrna_audit` is responsible for interpretation.

It should:

- read `provider_index.json`
- read `results/providers/*/annotation_result.json`
- normalize labels where possible
- visualize agreement, disagreement, and uncertainty
- link to provider-level Quarto/HTML reports
- produce review tables and report pages

It should not execute annotation providers.

## Planned Layout

```text
scrna_annotate/
  README.md
  DESIGN.md
  linkar_template.yaml
  run.sh                         # design-only placeholder for now
  config/
    dataset.toml                 # shared dataset contract
    providers.toml               # provider enablement and provider-specific config
  schema/
    annotation_result.schema.json
    provider_index.schema.json
  providers/
    README.md
    marker_based/provider_manifest.yaml
    celltypist/provider_manifest.yaml
    singler/provider_manifest.yaml
    manual_curated/provider_manifest.yaml
    mock_provider/provider_manifest.yaml
    scgpt/provider_manifest.yaml
    sctab/provider_manifest.yaml
  results/
    dataset_profile.json
    provider_index.json
    providers/
      marker_based/
        annotation_result.json
        report.qmd
        report.html
      celltypist/
        annotation_result.json
        report.qmd
        report.html
```

Provider code is deliberately absent in this scaffold. Future provider folders should add their
own `pixi.toml`, runner script, tests, and README only when implementation begins.

## Dataset Contract

All providers share a minimal dataset-level contract:

```toml
[dataset]
input_h5ad = "results/adata.prep.h5ad"
input_source_template = "scrna_prep"
organism = "human"
tissue = "blood"
cluster_key = "leiden"
sample_key = "sample_id"
batch_key = "batch"
condition_key = "condition"
gene_id_type = "gene_symbols"
expression_layer = "X"
raw_layer = "counts"
```

This describes the data. It should not contain provider-specific parameters.

The default Linkar binding may resolve `input_h5ad` from the latest `scrna_prep` output and fall
back to `scrna_integrate` only when a prep output is unavailable. Tissue should usually remain an
explicit user decision.

## Provider Configuration

Provider-specific requirements belong under provider-specific config blocks:

```toml
[providers.marker_based]
enabled = true
top_n_markers = 50
min_log2fc = 0.25

[providers.celltypist]
enabled = true
model = "Immune_All_Low.pkl"
majority_voting = true

[providers.scgpt]
enabled = false
model_path = ""
vocab_path = ""
use_gpu = false
```

This avoids pretending that marker databases, reference models, and foundation models all need the
same inputs.

## Provider Groups

Planned provider groups:

- `marker_based`: interpretable marker and marker-database methods
- `reference_based`: label transfer or pretrained reference model methods
- `atlas_model`: atlas-specific pretrained classifiers and mappers
- `foundation_model`: scGPT/scTab/Geneformer-style methods
- `llm_assisted`: explain-only marker interpretation
- `manual_curated`: user-provided labels or collaborator annotations
- `mock`: schema and audit test fixture

Default execution should remain conservative. Experimental providers must require explicit
configuration.

## Provider States

Every enabled or considered provider should write a JSON result with one of these states:

- `completed`
- `completed_with_warnings`
- `skipped`
- `needs_config`
- `failed`

Failed and skipped providers are part of the audit trail. They should not disappear.

## Standard Output

Each provider writes:

```text
results/providers/<provider_id>/annotation_result.json
```

Each provider may also write a method-level Quarto report:

```text
results/providers/<provider_id>/report.qmd
```

The `.qmd` file is the canonical human-readable report artifact. If Quarto is available in the
provider environment, the provider may also render:

```text
results/providers/<provider_id>/report.html
```

Missing HTML should not fail an otherwise successful provider. The provider should record a warning
when `report.qmd` is written but HTML rendering is unavailable.

The provider index records every provider and the location of its result:

```text
results/provider_index.json
```

The schema is in [schema/annotation_result.schema.json](schema/annotation_result.schema.json).

Provider reports should be registered in the `artifacts.reports` section of
`annotation_result.json` so `scrna_audit` can link to them without parsing provider-specific
report internals.

## First Implementation Milestone

The recommended MVP is:

1. dataset profiler
2. provider manifest reader
3. schema validation
4. `mock_provider`
5. `marker_based`
6. `provider_index.json`

After that, implement `scrna_audit` against the JSON contract before adding many real providers.

The first real provider set should probably be:

- `marker_based`
- `celltypist`
- `manual_curated`

Then add:

- `singler`
- `sctype`
- `sccatch`

Foundation models such as `scgpt` and `sctab` should come later, once model/vocabulary provenance
and validation warnings are stable.
