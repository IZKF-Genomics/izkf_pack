# scrna_annotate design

This document records the implementation contract before code is written.

## Problem

Single-cell annotation tools do not share one input model.

Some methods need marker tables, some need cell-level expression, some need a reference atlas, and
foundation models need model checkpoints, vocabularies, normalization assumptions, and hardware
choices. A single flat template interface would either hide those differences or become impossible
to maintain.

The design therefore uses:

1. a shared dataset contract
2. provider-specific manifests and config
3. a resolver/validation layer
4. one standard provider JSON schema
5. provider-level human-readable reports
6. a separate audit template

## Dataset Contract

The dataset contract describes the input object and common biological context.

Required fields:

- `input_h5ad`
- `cluster_key`

Recommended context fields:

- `organism`
- `tissue`
- `sample_key`
- `batch_key`
- `condition_key`
- `gene_id_type`
- `expression_layer`
- `raw_layer`

The resolver should inspect the `.h5ad` and write `results/dataset_profile.json` containing:

- `n_cells`
- `n_genes`
- `obs_columns`
- `var_columns`
- `layers`
- `obsm_keys`
- `has_umap`
- `cluster_key_exists`
- `gene_id_guess`
- `warnings`

Unknown tissue is a supported state. The resolver should not fail the template only because
`tissue` is empty. Instead, provider readiness should depend on the method:

- exploratory methods may run and record context-light warnings
- tissue-specific reference or marker-database methods may become `needs_config`
- reports should make clear that missing tissue lowers interpretability and confidence

## Provider Manifest

Each provider declares its own requirements in `provider_manifest.yaml`.

The manifest should include:

- provider id and display name
- provider group
- maturity level
- default enablement
- environment manager
- planned entrypoint
- input requirements
- configuration keys
- output contract
- known limitations

The resolver uses manifests to decide whether a provider is `ready`, `needs_config`, `skipped`, or
`failed`.

Provider methods may be organism-independent, but resources are organism-aware. A marker catalog,
reference atlas, or model must declare its organism/species. A provider must not silently apply a
resource across organisms; mismatches should become `needs_config` unless a future provider has an
explicit ortholog-mapped catalog with recorded provenance.

## Dependency Boundary

The top-level template may provide a small shared environment for common Python/scverse utilities,
but provider-specific dependencies should stay provider-owned when they become heavy or conflicting.

The intended pattern is:

```text
run.py                         # generic orchestration
lib/                           # shared config, IO, profiling, report rendering
providers/<provider_id>/       # provider computation, optional provider pixi.toml, report.qmd
```

The top-level runner should not grow direct imports for every annotation tool. New providers should
be added through a provider runner registry and their own provider folder.

## Cache Boundary

The first marker-based MVP does not use external database cache.

Future database-backed providers must treat cached files as provider data artifacts, not project
outputs. Cache provenance should be recorded in `annotation_result.json`, including source URL,
local cache path, checksum, and refresh/download metadata when available.

Recommended policy:

- explicit user files are read in place and not cached
- public databases may be downloaded to a user-level cache
- cached public databases are reused by default
- remote refresh is explicit
- provider output records the exact database checksum used

## Requirement Types

Provider requirements should be expressed by category.

Expression requirements:

- raw counts
- normalized log1p expression
- scaled expression
- cluster marker table
- cell-level expression
- cluster-level summaries

Gene requirements:

- gene symbols
- Ensembl ids
- model vocabulary overlap
- ortholog mapping

Metadata requirements:

- organism
- tissue, optional for exploratory methods and required only when a provider is tissue-specific
- cluster key
- sample key
- batch key
- condition key

Reference/model requirements:

- pretrained model name
- local model path
- reference h5ad
- label key
- vocabulary path
- checkpoint hash

Hardware requirements:

- CPU-only
- optional GPU
- required GPU
- memory warnings

## Provider Groups

### marker_based

Examples:

- internal marker scoring
- local organism-aware marker catalog scoring
- scType
- scCATCH
- SCINA
- Garnett
- CellAssign

These methods are interpretable and should be early implementation targets.

### reference_based

Examples:

- CellTypist
- SingleR
- CHETAH
- scmap
- scPred
- Seurat label transfer
- Azimuth
- Symphony
- scArches

These methods require reference/model provenance.

### foundation_model

Examples:

- scGPT
- scTab
- Geneformer
- UCE
- scFoundation
- scBERT

These must remain experimental until model, vocabulary, and preprocessing validation are explicit.

### llm_assisted

Examples:

- marker-list explanation
- literature-assisted label suggestions

These should produce explanatory evidence, not authoritative final labels.

### manual_curated

Examples:

- collaborator labels
- existing labels in `adata.obs`
- review CSV
- manuscript labels

Manual labels should be treated as a provider so the audit report can compare automated and human
annotation sources.

## Annotation Unit

The schema supports both cell-level and cluster-level predictions.

Cluster-level predictions are the preferred audit unit. Providers that produce cell-level labels
should aggregate to clusters and record the aggregation rule.

Example aggregation metadata:

```json
{
  "from": "cell_predictions",
  "to": "cluster_predictions",
  "rule": "majority_vote",
  "cluster_key": "leiden"
}
```

## Label Representation

Provider results should preserve both raw and normalized labels:

- `label_raw`
- `label_normalized`
- `ontology_id`

`ontology_id` is optional in the first implementation but should remain in the schema.

## Scores and Confidence

Numeric scores are provider-specific and should not be compared directly across providers.

Each candidate should record:

- `provider_score`
- `provider_score_name`
- `confidence_bucket`

The audit template may compare confidence buckets, ranks, and label agreement, but should not treat
CellTypist probability, marker overlap, SingleR delta, and foundation-model softmax as equivalent.

## Failure Policy

Bad dataset-level configuration should fail early.

Provider-specific missing config should not fail the whole template. The provider should write a
`needs_config` result with explicit missing fields.

Provider runtime errors should write a `failed` result when possible.

## Provider Reports

Each provider may emit a method-level Quarto report.

The canonical human-readable report source is:

```text
results/providers/<provider_id>/report.qmd
```

Rendered HTML is optional:

```text
results/providers/<provider_id>/report.html
```

The provider-level report should explain method-specific evidence and diagnostics that do not fit
cleanly into the shared JSON schema. Examples include:

- marker-based matched and missing genes
- CellTypist probability and majority-vote diagnostics
- SingleR score margins
- reference or model provenance
- provider-specific warnings and skipped assumptions

`annotation_result.json` remains the required machine-readable contract. A missing Quarto renderer
should not make a successful annotation fail. In that case, the provider should write `report.qmd`,
omit `report.html`, and record a warning such as:

```text
Quarto is not available; report.qmd was written but was not rendered to HTML.
```

Provider reports are allowed to have method-specific structure. They should not become the data
contract between templates. `scrna_audit` should link to provider reports, but it should read only
`annotation_result.json` and `provider_index.json` for comparison logic.

## Presets

Presets should enable known-safe provider groups. `all` should mean all enabled providers, not all
available providers.

Initial planned presets:

- `default`: marker-based plus safe low-setup providers
- `immune_basic`: marker-based plus CellTypist immune model when configured
- `manual_review`: manual labels plus marker evidence
- `experimental_foundation`: explicitly configured foundation-model providers only

## Relationship to scrna_audit

`scrna_audit` will consume:

- `results/dataset_profile.json`
- `results/provider_index.json`
- `results/providers/*/annotation_result.json`
- provider report artifact links recorded by each provider

It will produce:

- provider status table
- cluster-by-provider comparison table
- agreement and conflict summaries
- consensus suggestions
- review-priority table
- benchmark and review Quarto/HTML report

It should not parse provider report internals or recompute method-specific diagnostics.

`scrna_audit` should not run providers.
