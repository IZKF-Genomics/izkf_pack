# nf-core template conventions

This pack uses a consistent pattern for the nf-core style templates, especially:

- [`nfcore_3mrnaseq`](../templates/nfcore_3mrnaseq/README.md)
- [`nfcore_methylseq`](../templates/nfcore_methylseq/README.md)
- [`nfcore_scrnaseq`](../templates/nfcore_scrnaseq/README.md)

The goal is to make the final command easy to inspect, rerun, and cite later in
methods generation.

These templates also rely on facility-managed shared references and binaries
prepared by the companion repository
[`genomics-assets`](https://github.com/IZKF-Genomics/genomics-assets). In
practice, `izkf_pack` consumes paths such as `/data/ref_genomes/...` and
`/data/shared/10xGenomics/...`, while `genomics-assets` is responsible for
building or fetching them.

## Preferred launcher pattern

For these templates, the preferred design is:

1. `run.py` resolves parameters and metadata
2. `run.py` writes a concrete `run.sh`
3. `run.py` records runtime artifacts
4. the generated `run.sh` contains the exact command the user can inspect or rerun

This is easier for users than hiding the final command deep inside Python logic.

## What the generated run.sh should look like

The rendered `run.sh` should be:

- human-readable
- multiline
- easy to edit
- based on relative paths when possible

Good examples:

- `-c nextflow.config`
- `--input samplesheet.csv`
- `--outdir results`

Instead of absolute project paths in every flag.

## Recorded provenance

These templates should also emit machine-readable provenance, especially:

- `runtime_command.json`
- `software_versions.json`

That combination is useful for:

- methods generation
- export
- reproducibility checks
- debugging differences between runs

## Facility-specific convenience behavior

The pack also supports facility shorthands in some nf-core templates, such as:

- `umi=true`
- `spikein=true`

These are user conveniences, but downstream methods text should still reflect
the resolved technical value or the actual rendered command.

## Why command recording matters

For this pack, the command is not just an execution detail. It is also the most
reliable source for later interpretation. For example:

- whether UMI extraction was really enabled
- which effective genome was used
- which nf-core revision was run
- which extra aligner or quantification arguments were applied

That is why downstream consumers such as `methods` should prefer
`runtime_command.json` when it is available.

## Recommended maintenance rule

When editing nf-core templates in this pack:

- keep `run.sh` readable first
- keep `runtime_command.json` complete
- avoid duplicating command truth across too many places
- prefer visible workspace files over hidden history paths when users inspect runs

## Related docs

- [facility_defaults.md](facility_defaults.md)
- [template_outputs.md](template_outputs.md)
- [methods.md](methods.md)
