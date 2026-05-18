# scrna_annotate design notes

The [`scrna_annotate`](../templates/scrna_annotate/README.md) template has been reset to a
design-only scaffold for a provider-based annotation architecture.

No annotation provider code is implemented in this scaffold yet. The purpose of the current
directory is to define the interface, output schema, provider manifest model, and implementation
sequence before writing execution code.

## Architecture

The planned model separates execution from interpretation:

- `scrna_annotate` runs independent annotation providers.
- Each provider writes one standard `annotation_result.json`.
- Each provider may write a method-level Quarto report.
- `scrna_audit` will read the JSON files, link provider reports, and create comparisons,
  consensus summaries, benchmark pages, and review tables.

This boundary is important. Annotation methods have different assumptions and input requirements,
so the audit layer should not hide those differences by recomputing or silently filling in missing
provider results.

## Why the old tiered design was removed

The previous `scrna_annotate` template used a tiered preview/refinement/formal structure. That was
useful as a user-experience experiment, but it mixed several concerns:

- workflow orchestration
- method execution
- preview labels
- formal reference-aware annotation
- reporting and review

The new plan is cleaner:

- one provider runner template
- provider-owned method reports
- one audit and benchmark reporting template
- one provider JSON contract between them

## Provider groups

Planned provider groups:

| Group | Examples | Default? | Notes |
| --- | --- | --- | --- |
| `marker_based` | marker overlap, scType, scCATCH, SCINA, Garnett, CellAssign | yes, conservative | Best first target because evidence is inspectable. |
| `reference_based` | CellTypist, SingleR, CHETAH, scmap, scPred, Seurat label transfer | optional | Requires explicit model/reference provenance. |
| `atlas_model` | Azimuth, Symphony, scArches, custom atlas classifier | optional | Needs atlas version and label-space metadata. |
| `foundation_model` | scGPT, scTab, Geneformer, UCE, scFoundation, scBERT | experimental | Requires model checkpoint, vocabulary, preprocessing, and hardware provenance. |
| `llm_assisted` | marker-list interpretation, literature-assisted explanation | optional | Should explain evidence, not act as sole source of truth. |
| `manual_curated` | collaborator labels, manuscript labels, review CSV | optional | Human labels should be first-class provider evidence. |
| `mock` | schema test provider | test only | Useful for building `scrna_audit` before real providers exist. |

## Input requirement strategy

Do not force all methods into one flat parameter set.

Use three layers:

1. Dataset contract
2. Provider-specific config
3. Resolver and validation layer

The dataset contract describes the data:

- `input_h5ad`
- `organism`
- `tissue`
- `cluster_key`
- `sample_key`
- `batch_key`
- `condition_key`
- `gene_id_type`
- `expression_layer`
- `raw_layer`

Provider-specific config describes the method:

- CellTypist model
- SingleR reference
- marker database settings
- manual label CSV
- scGPT/scTab checkpoint and vocabulary paths

The resolver should inspect the `.h5ad`, check provider manifests, and classify each provider as:

- `completed`
- `completed_with_warnings`
- `skipped`
- `needs_config`
- `failed`

## Output contract

Every provider writes:

```text
results/providers/<provider_id>/annotation_result.json
```

Every provider may also write:

```text
results/providers/<provider_id>/report.qmd
results/providers/<provider_id>/report.html
```

The Quarto source is the canonical human-readable method report. Rendered HTML is optional and
should not be required for a successful annotation run. If Quarto is unavailable, a provider should
write `report.qmd`, omit `report.html`, and record a warning in `annotation_result.json`.

Provider reports are for method-specific evidence and diagnostics. For example, a marker-based
provider can show matched and missing marker genes, while a reference-based provider can show model
or reference provenance and score diagnostics. The audit template should link to these reports, but
it should not parse them as input data.

The top-level runner writes:

```text
results/dataset_profile.json
results/provider_index.json
```

The JSON contract must represent both successful and unsuccessful providers. A skipped provider is
still useful because it explains why a method was not run.

## Annotation units

The schema supports:

- `cluster_predictions`
- `cell_predictions`

Cluster-level prediction is the preferred audit unit. Providers that produce cell-level labels
should aggregate to clusters and record the aggregation rule.

## Label handling

Provider output should preserve:

- raw provider label
- normalized label
- optional ontology id

String comparison alone is not enough because tools may emit labels such as `CD4 T cell`,
`CD4+ T-cell`, or `T helper cell`.

## Score handling

Provider scores are not comparable across methods.

The schema therefore records:

- `provider_score`
- `provider_score_name`
- `confidence_bucket`

The audit layer may compare rank and confidence bucket, but should not compare numeric values
across CellTypist probabilities, marker overlap scores, SingleR deltas, and foundation-model
softmax scores as though they were the same.

## Foundation model rules

Foundation-model providers such as scGPT and scTab should stay disabled by default.

They must record:

- model path or name
- model revision or checkpoint hash
- vocabulary path or hash
- gene vocabulary overlap
- expression layer and normalization assumption
- hardware mode
- label space

Low vocabulary overlap should become a provider warning and later a visible `scrna_audit` warning.

## Recommended milestone

First milestone:

1. dataset profiler
2. provider manifest reader
3. JSON schema validation
4. `mock_provider`
5. `marker_based`
6. `provider_index.json`

Second milestone:

1. `scrna_audit` reader
2. provider status report
3. cluster-by-provider comparison
4. conflict/review table

Only then add more real providers.

## Files

- [Template README](../templates/scrna_annotate/README.md)
- [Design document](../templates/scrna_annotate/DESIGN.md)
- [Dataset config draft](../templates/scrna_annotate/config/dataset.toml)
- [Providers config draft](../templates/scrna_annotate/config/providers.toml)
- [Annotation result schema](../templates/scrna_annotate/schema/annotation_result.schema.json)
- [Provider index schema](../templates/scrna_annotate/schema/provider_index.schema.json)
- [Provider manifests](../templates/scrna_annotate/providers/README.md)
