# scrna_annotate design notes

The [`scrna_annotate`](../templates/scrna_annotate/README.md) template is now a provider-based
annotation architecture with a marker-based MVP.

The current implementation runs `marker_based` and can optionally run `marker_catalog`. The
remaining providers are explicit planned interfaces. This lets real datasets produce standard
provider JSON now while the broader annotation ecosystem is added incrementally.

The template intentionally treats `input_h5ad` as a string parameter that is resolved to a path at
runtime. This keeps large upstream outputs from `scrna_prep` or `scrna_integrate` in place while
still recording the resolved input path in provider JSON.

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
| `marker_based` | differential markers, organism-aware marker catalog overlap, future scType/scCATCH/SCINA/Garnett/CellAssign | yes, conservative | MVP implemented for differential markers, human-only built-in signatures, and optional local marker catalogs. |
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

`tissue` is optional at the template level. Missing tissue should not block exploratory providers.
Instead, providers should report context-light evidence and make the reduced confidence visible.
Tissue-specific marker databases, reference atlases, or pretrained tissue models should require an
explicit tissue or explicit model/reference configuration.

Provider-specific config describes the method:

- local marker catalog path and species
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

Provider methods can be organism-independent, but resources must be organism-aware. If a dataset is
zebrafish, a human marker catalog should not run unless a future explicit ortholog-mapped catalog
provider records the mapping source and version.

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

The top-level `run.py` is intentionally thin. Shared configuration, dataset profiling, JSON/CSV
writing, report rendering, and provider indexing live under `templates/scrna_annotate/lib/`.
Provider-specific computation and report sources live in each provider folder.

The current `marker_based` provider writes:

```text
results/providers/marker_based/annotation_result.json
results/providers/marker_based/report.qmd
results/providers/marker_based/report.html
results/providers/marker_based/tables/differential_markers.csv
results/providers/marker_based/tables/marker_signatures.csv
results/providers/marker_based/tables/marker_strength_summary.csv
```

When enabled, the current `marker_catalog` provider reads an explicit local TSV catalog and writes:

```text
results/providers/marker_catalog/annotation_result.json
results/providers/marker_catalog/tables/catalog_matches.csv
```

Catalog resources are described separately from provider execution in
`templates/scrna_annotate/config/catalog_resources.toml`. The provider consumes a resolved TSV
catalog; future downloaders should download/cache/convert/verify resources before annotation.

The rendered marker report is intended as the first manual review surface. It includes full warning
messages, interactive Plotly figures when available, compact review tables, top signature matches,
differential markers, method details, and citations. Report tables are rendered with sorting,
search, column filters, and pagination when itables is available. If Plotly or itables is missing,
the report should still render with text or static-table fallbacks.

Long tables should not be dumped unbounded into the report. The provider report should:

- show review-friendly columns first
- clip long gene-list cells for readability
- paginate large tables
- keep full CSV artifacts for exhaustive inspection

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

Completed first milestone:

1. dataset profiler
2. marker-based provider execution
3. standard provider JSON
4. provider-level Quarto report
5. provider index

Next implementation milestone:

1. `scrna_audit` reader
2. provider status report
3. cluster-by-provider comparison
4. conflict/review table
5. `user_markers` provider
6. cached external marker database providers

Only then add more real providers.

## Test run

From the rendered template workspace:

```bash
INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=human \
CLUSTER_KEY=leiden \
./run.sh
```

Unknown tissue is supported:

```bash
INPUT_H5AD=/path/to/adata.prep.h5ad \
ORGANISM=zebrafish \
CLUSTER_KEY=leiden \
./run.sh
```

The second example should run in context-light mode and record warnings instead of failing. For
zebrafish, built-in human marker signatures are skipped to avoid cross-species misannotation.
Zebrafish annotation should use a species-specific marker database, a zebrafish reference atlas, or
an explicit ortholog-mapped marker catalog.

Local zebrafish marker catalog scoring can be enabled with:

```toml
[providers.marker_catalog]
enabled = true
resource_id = "zebrafish_example"
catalog_path = "config/marker_catalogs/zebrafish.example.tsv"
species = "zebrafish"
min_matched_genes = 2
```

The example catalog is only a schema/example fixture. Replace it with project-specific markers and
citations before interpreting biological labels.

Future downloadable catalogs should use `SCRNA_ANNOTATE_CACHE_DIR`, defaulting to
`~/.cache/izkf_pack/scrna_annotate/catalogs`, and should record source URL, release/version,
converted TSV checksum, species, and citation.

## Files

- [Template README](../templates/scrna_annotate/README.md)
- [Design document](../templates/scrna_annotate/DESIGN.md)
- [Dataset config draft](../templates/scrna_annotate/config/dataset.toml)
- [Providers config draft](../templates/scrna_annotate/config/providers.toml)
- [Annotation result schema](../templates/scrna_annotate/schema/annotation_result.schema.json)
- [Provider index schema](../templates/scrna_annotate/schema/provider_index.schema.json)
- [Provider manifests](../templates/scrna_annotate/providers/README.md)
