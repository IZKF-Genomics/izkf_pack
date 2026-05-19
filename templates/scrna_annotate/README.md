# scrna_annotate

Status: marker-based MVP.

This directory defines the planned architecture for a provider-based single-cell RNA-seq
annotation runner. The old tiered implementation has been removed and replaced by a first
provider-based implementation that runs marker-gene evidence against prepared `.h5ad` files.

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
- require tissue metadata for exploratory providers that can still produce useful evidence
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
  pixi.toml
  run.py                         # thin orchestration only
  run.sh
  config/
    dataset.toml                 # shared dataset contract
    providers.toml               # provider enablement and provider-specific config
    catalog_resources.toml       # marker catalog resource/cache registry
    marker_catalogs/
      zebrafish.example.tsv      # local organism-aware marker catalog example
  schema/
    annotation_result.schema.json
    provider_index.schema.json
  lib/
    config.py
    dataset.py
    io.py
    provider_index.py
    provider_runner.py
    reports.py
  providers/
    README.md
    marker_based/
      core.py
      marker_signatures.py
      provider_manifest.yaml
      report.qmd
      run.py
    marker_catalog/
      core.py
      provider_manifest.yaml
      run.py
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

`marker_based` and `marker_catalog` have execution code in the first MVP. The top-level runner stays
generic: provider-specific computation lives in provider folders, and shared utility code lives
under `lib/`. Other provider manifests remain as planned interfaces and are written as
disabled/skipped provider results unless enabled provider code is added later.

## Dependency Model

The MVP uses one template-level `pixi.toml` environment. This keeps the first provider easy to run
and makes local testing predictable. It includes Scanpy for marker ranking, Quarto/Jupyter for
report rendering, Plotly for interactive figures, and itables for searchable/filterable HTML
tables.

Future providers should declare their dependency expectations in `provider_manifest.yaml`. When a
provider needs heavy, conflicting, or language-specific dependencies, add a provider-local
environment rather than expanding the shared environment indefinitely:

```text
providers/<provider_id>/
  provider_manifest.yaml
  pixi.toml
  run.py
  report.qmd
```

The top-level runner should remain responsible for orchestration only. It should not import tool
APIs such as CellTypist, SingleR, scGPT, or database readers directly.

## Cache Model

The MVP does not use any external marker database cache. The `marker_based` provider can use
built-in human broad marker signatures only for human datasets. The `marker_catalog` provider reads
explicit local TSV catalogs and records the catalog path/species in provider JSON.

Catalog resources are described in `config/catalog_resources.toml`. This manifest is the planned
connection point for local and downloaded catalogs. The annotation provider consumes a resolved TSV;
download, conversion, refresh, and checksum validation should stay in a separate resource/cache
layer.

Database-backed providers such as `user_markers`, `cellmarker`, and `panglaodb` should be added as
separate providers. Their cache rules should be explicit in provider config and provider JSON:

- user-provided marker files are read from explicit paths and are not cached
- downloaded public databases should live outside the project workspace
- the cache directory should come from `SCRNA_ANNOTATE_CACHE_DIR`, defaulting to
  `~/.cache/izkf_pack/scrna_annotate/catalogs`
- cached database files must record source URL, local path, download time when available, and
  sha256 checksum in `annotation_result.json`
- refresh should be explicit, not automatic during every annotation run

## Run

Set the prepared `.h5ad` path and run the template workspace:

```bash
INPUT_H5AD=/path/to/adata.prep.h5ad CLUSTER_KEY=leiden ./run.sh
```

`input_h5ad` is intentionally declared as a string parameter in `linkar_template.yaml`. The
template treats it as a path at runtime and reads the upstream file in place, instead of asking
Linkar to stage/copy the `.h5ad` into this workspace.

Optional runtime overrides:

```bash
ORGANISM=human \
INPUT_H5AD=/path/to/adata.prep.h5ad \
CLUSTER_KEY=leiden \
TOP_N_MARKERS=50 \
MIN_LOG2FC=0.25 \
./run.sh
```

Enable a local organism-aware marker catalog without editing TOML:

```bash
ORGANISM=zebrafish \
INPUT_H5AD=/path/to/adata.prep.h5ad \
CLUSTER_KEY=leiden \
MARKER_CATALOG_ENABLED=true \
MARKER_CATALOG_RESOURCE_ID=zebrafish_example \
MARKER_CATALOG_PATH=config/marker_catalogs/zebrafish.example.tsv \
MARKER_CATALOG_SPECIES=zebrafish \
./run.sh
```

`TISSUE` is optional. If it is not set, the runner prints a context-light message and the
marker-based provider records a warning instead of failing. Add `TISSUE=blood`, `TISSUE=brain`, or
another explicit context once it is known.

The marker-based MVP writes:

```text
results/dataset_profile.json
results/provider_index.json
results/providers/marker_based/annotation_result.json
results/providers/marker_based/report.qmd
results/providers/marker_based/report.html
results/providers/marker_based/tables/differential_markers.csv
results/providers/marker_based/tables/marker_signatures.csv
results/providers/marker_based/tables/marker_strength_summary.csv
```

When `marker_catalog` is enabled, it also writes:

```text
results/providers/marker_catalog/annotation_result.json
results/providers/marker_catalog/tables/catalog_matches.csv
```

If Quarto is unavailable, `report.qmd` is still written and the missing HTML render is recorded as
a provider warning.

## Quick Test Checklist

From this template directory:

```bash
cd /home/ckuo/github/izkf_pack/templates/scrna_annotate
INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=human \
CLUSTER_KEY=leiden \
./run.sh
```

For an exploratory run with unknown tissue, leave `TISSUE` unset. The run should still produce:

- `results/provider_index.json`
- `results/providers/marker_based/annotation_result.json`
- `results/providers/marker_based/report.html` when Quarto renders successfully
- `results/providers/marker_based/tables/*.csv`

Inspect the report first. The marker-based provider is designed to surface candidate labels,
matched genes, missing genes, marker strength, and warnings for manual review.

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
back to `scrna_integrate` only when a prep output is unavailable. Tissue is optional because many
exploratory analyses start before the biological context is fully known. Providers should treat
missing tissue as reduced context, not as a template-wide failure.

Recommended behavior when `tissue = ""`:

- exploratory providers such as broad marker evidence may run and record a warning
- tissue-specific marker databases or atlas references should either ask for explicit config or
  write `needs_config`
- reports should label the evidence as context-light and avoid presenting final annotations

For zebrafish, also keep `organism = "zebrafish"` even when tissue is unknown. The current built-in
signatures are human signatures and are skipped for zebrafish to avoid cross-species
misannotation. Zebrafish annotation should use a species-specific marker database, a zebrafish
reference atlas, or an explicit ortholog-mapped marker catalog.

The first zebrafish MVP path is an explicit local catalog:

```toml
[providers.marker_catalog]
enabled = true
catalog_path = "config/marker_catalogs/zebrafish.example.tsv"
species = "zebrafish"
min_log2fc = 0.25
min_matched_genes = 2
```

Copy the example catalog before using it for real annotation and replace the example rows with
project-appropriate markers and citations.

The local catalog TSV schema is documented in
`config/marker_catalogs/README.md`. The resource/cache registry is documented in
`config/catalog_resources.toml`.

Future downloadable catalogs should follow this flow:

1. add a resource entry in `config/catalog_resources.toml`
2. download to `SCRNA_ANNOTATE_CACHE_DIR`
3. convert to `marker_catalog_tsv`
4. verify SHA256
5. run `marker_catalog` with the resolved TSV path
6. record resource id, path, species, and checksum in `annotation_result.json`

## Provider Configuration

Provider-specific requirements belong under provider-specific config blocks:

```toml
[providers.marker_based]
enabled = true
top_n_markers = 50
min_log2fc = 0.25

[providers.marker_catalog]
enabled = true
catalog_path = "config/marker_catalogs/zebrafish.example.tsv"
species = "zebrafish"
min_matched_genes = 2

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

Provider methods can be organism-independent, but resources cannot be implicit. Every marker
catalog, reference atlas, and model should declare its organism. If the dataset organism and
resource organism do not match, the provider should write `needs_config` rather than silently
running across species.

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

The marker-based HTML report includes:

- run context and full provider warning messages
- compact cluster review table with sorting, search, filters, and pagination
- interactive marker-strength, signature heatmap, and marker-evidence figures when Plotly is available
- compact signature and marker tables with sorting, search, filters, and pagination
- method details and citations

Long tables are optimized by showing review-friendly columns, clipping long gene-list cells, and
paginating the HTML display. Full tables remain available as CSV artifacts under
`results/providers/marker_based/tables/`.

The provider index records every provider and the location of its result:

```text
results/provider_index.json
```

The schema is in [schema/annotation_result.schema.json](schema/annotation_result.schema.json).

Provider reports should be registered in the `artifacts.reports` section of
`annotation_result.json` so `scrna_audit` can link to them without parsing provider-specific
report internals.

## Implementation Milestones

Completed in the first MVP:

1. dataset profiler
2. standard `annotation_result.json`
3. provider state indexing
4. `marker_based` differential marker evidence
5. built-in human marker signature scoring for human datasets only
6. local organism-aware marker catalog scoring
7. provider-level Quarto report
8. `provider_index.json`

Recommended next steps:

1. implement `scrna_audit` against the JSON contract
2. add `user_markers` as the next marker database provider
3. add cached external marker database providers such as CellMarker and PanglaoDB
4. add CellTypist and SingleR once reference/model provenance is stable

The first real provider set should probably be:

- `marker_based`
- `user_markers`
- `marker_catalog`
- `celltypist`
- `manual_curated`

Then add:

- `singler`
- `sctype`
- `sccatch`

Foundation models such as `scgpt` and `sctab` should come later, once model/vocabulary provenance
and validation warnings are stable.
