# scverse_scrna_prep workspace notes

The [`scverse_scrna_prep`](../templates/scverse_scrna_prep/README.md) template
creates an editable Scanpy-based preprocessing workspace for single-cell RNA-seq
data.

This document collects the pack-specific assumptions that are easy to miss when
reading only the template README.

## Accepted input styles

The template supports several input modes, including:

- `.h5ad`
- 10x HDF5
- 10x MTX directories
- ParseBio outputs
- ScaleBio or STARsolo-style MTX layouts
- Cell Ranger `per_sample_outs`

At least one of `input_h5ad` or `input_matrix` must be set.

## organism is required

The template expects `organism` to be set explicitly so QC gene annotation can
use the correct mitochondrial, ribosomal, and hemoglobin naming rules.

Examples:

- `human`
- `mouse`
- `hsapiens`
- `mmusculus`

## Raw-count expectation for `.h5ad`

This is the most important workflow assumption.

When `.h5ad` is used as input, the preprocessing notebook expects raw counts.
That is because the workspace performs steps such as:

- Scrublet doublet scoring
- QC thresholding
- normalization
- log transformation
- HVG selection
- PCA and clustering

If `adata.X` already contains normalized values, the results would be misleading.

Current pack behavior:

- if `adata.layers["counts"]` exists, it is used as the raw count matrix
- otherwise the template checks whether `adata.X` looks like raw counts
- if not, the run stops with a clear error

## Sample metadata behavior

Optional sample metadata can be provided as a CSV with a `sample_id` column.
When present, it is merged into `adata.obs` and can supply columns such as:

- batch
- condition
- sample labels
- patient identifiers

If expected columns are missing, the workspace falls back to `"unknown"` for the
requested keys instead of silently failing later.

## QC modes

The template currently supports:

- `fixed`
- `mad_per_sample`

This gives users a simple threshold-based path and a sample-aware outlier path.

## Output expectations

Important outputs include:

- `results/adata.prep.h5ad`
- `results/tables/*.csv`
- `results/run_info.yaml`
- `results/software_versions.json`
- `reports/00_qc.html`

## Maintenance notes

When editing this template, treat these as high-sensitivity areas:

- input-format detection
- raw-count handling for `.h5ad`
- sample metadata joining
- QC pass logic
- report outputs that downstream templates may export later

## Related docs

- [template_outputs.md](template_outputs.md)
- [software_versions.md](software_versions.md)
