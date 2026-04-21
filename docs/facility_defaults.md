# facility defaults in izkf_pack

Some behavior in this pack reflects facility-specific conventions rather than
generic Linkar behavior.

Documenting those assumptions helps template maintenance and makes the pack
easier to understand for collaborators.

## Common metadata-driven defaults

Examples used in this pack include:

- UMI labels resolved from Agendo metadata
- spike-in labels resolved from Agendo metadata
- organism or genome mapping helpers
- archive destination roots

These defaults are useful, but they should be applied in a way that still makes
the final workspace understandable to users.

## UMI and spike-in shorthands

Some templates support user-friendly shorthands such as:

- `--param umi=true`
- `--param spikein=true`

These are pack conveniences. Internally they resolve to the facility’s standard
descriptive labels.

That means:

- the CLI stays short for facility users
- the resulting metadata and methods text can still use the full technical names

## Agendo and metadata API assumptions

Several templates use helper functions or API enrichment to resolve:

- genome
- UMI metadata
- spike-in metadata
- assay context

Those values improve defaults, but later reporting should still prefer the
actual rendered command when the question is “what really ran?”

## Shared reference asset assumptions

Several templates also assume facility-managed shared assets such as:

- `/data/ref_genomes/...`
- `/data/shared/10xGenomics/refs/...`
- `/data/shared/10xGenomics/bin/...`

Those assets are maintained in the companion repository
[`genomics-assets`](https://github.com/IZKF-Genomics/genomics-assets), not in
`izkf_pack` itself.

That split is intentional:

- `genomics-assets` builds or fetches shared references and binaries
- `izkf_pack` consumes those shared assets inside rendered Linkar workflows

## Archive paths

Archive templates in this pack also assume facility destinations such as:

- raw archive roots
- FASTQ archive roots
- project archive roots

These are pack-level operational defaults and should stay documented rather than
hidden only in code.

## Maintenance guideline

When adding a new facility default:

- keep the user-facing behavior simple
- preserve the full descriptive value in runtime artifacts when useful
- document it here if it affects more than one template

## Related docs

- [nfcore_templates.md](nfcore_templates.md)
- [project_history_and_archive.md](project_history_and_archive.md)
- [methods.md](methods.md)
