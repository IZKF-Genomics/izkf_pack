# Feature Reference variants

A Cell Ranger Feature Reference is a lookup table, not a genome reference. Each row connects an experimental oligo barcode to a named antibody, hashtag, guide, or antigen. The common required columns are:

```csv
id,name,read,pattern,sequence,feature_type
```

`id` and `name` must be unique ASCII labels without whitespace, slash, quote, or comma. `read` is `R1` or `R2`; `pattern` must contain exactly one `(BC)`; `sequence` is the actual barcode/protospacer sequence. `feature_type` must match the corresponding `feature_types` value in `config/samples.csv`.

Official specification: <https://www.10xgenomics.com/support/software/cell-ranger/latest/tutorials/inputs/cr-feature-ref-csv>

## TotalSeq-A antibody capture

- Typical assays: legacy/unsupported CITE-seq workflows and 10x 3′ v2/v3 where appropriate.
- Typical layout: `R2`, `5P(BC)` (also written `^(BC)`).
- Feature type: `Antibody Capture`.
- Do not select it for a 5′ experiment merely because an A barcode sequence resembles a C barcode.

```csv
id,name,read,pattern,sequence,feature_type
__ANTIBODY_ID__,__ANTIBODY_NAME__,R2,5P(BC),__BARCODE__,Antibody Capture
```

## TotalSeq-B antibody capture

- Typical assay: 10x 3′ Gene Expression with cell-surface protein Feature Barcoding.
- Typical layout: `R2`, `5PNNNNNNNNNN(BC)`.
- Feature type: `Antibody Capture`.
- Use only B reagents actually present in the experiment.

## TotalSeq-C antibody capture

- Typical assay: 10x 5′ Gene Expression/Immune Profiling with cell-surface protein Feature Barcoding.
- Typical layout: `R2`, `5PNNNNNNNNNN(BC)`.
- Feature type: `Antibody Capture`.
- This is the likely family for GEM-X 5′ v3 protocol CG000734, but the reagent label/panel remains authoritative.

```csv
id,name,read,pattern,sequence,feature_type
__ANTIBODY_ID__,__ANTIBODY_NAME__,R2,5PNNNNNNNNNN(BC),__BARCODE__,Antibody Capture
```

## Sample hashing

Hashing reagent layout follows its TotalSeq family: A uses its A layout; B/C use their B/C layout. Starting with Cell Ranger 9, antibody hashing is represented as `Antibody Capture` in both the Feature Reference and the `[libraries]` section. Add a `[samples]` section with `sample_id,hashtag_ids`; the IDs must exactly match Feature Reference `id` values. `Multiplexing Capture` is reserved for 10x CellPlex/CMO libraries.

Do not combine protein ADTs and hashtag rows blindly. Confirm whether they were sequenced as one or separate Feature Barcode libraries and set each library's `feature_types` accordingly. A target depth around 500 reads/cell is characteristic of hashing; a broad protein panel usually needs materially greater depth.

## PTG antibody capture

- Used primarily with compatible Flex protein workflows.
- Typical layout: `R2`, `5P(BC)`.
- Feature type: `Antibody Capture`.
- Use the PTG-supplied panel file; do not translate TotalSeq names into PTG sequences.

## Custom antibody conjugates

Use the exact oligo-order/conjugation record. For 10x-compatible custom conjugates, the barcode may come from the 10x Feature Barcode inclusion list (CG000193), but the experiment-specific mapping from barcode to antibody is still required. Select `source = "file"`.

10x labeling guidance: <https://www.10xgenomics.com/support/universal-five-prime-gene-expression/documentation/steps/sample-prep>

## dMHC Dextramer or multimer reagents

Immudex dCODE Dextramers used as an Antibody Capture-style feature may share the TotalSeq-C read pattern, but names and barcode sequences must come from the purchased panel. Do not confuse this with BEAM Antigen Capture.

## 3′ CRISPR Guide Capture

- Feature type: `CRISPR Guide Capture`.
- Required extra columns: `target_gene_id,target_gene_name`.
- `sequence` is the guide/protospacer sequence.
- The pattern contains the assay-specific downstream guide-RNA anchor, for example `(BC)<anchor>`.
- Obtain guides and target mapping from the perturbation design; there is no universal guide catalog.

## 5′ CRISPR Guide Capture

- Feature type: `CRISPR Guide Capture`.
- Required extra columns: `target_gene_id,target_gene_name`.
- Relative to 3′ capture, the guide sequence and anchor orientation must follow the official 5′ example (reverse-complement orientation where specified).
- Never convert a 3′ guide reference by changing only the label.

## BEAM-T and BEAM-Ab Antigen Capture

- Feature type: `Antigen Capture`.
- BEAM-T references may require `mhc_allele`; BEAM workflows have additional experiment-specific antigen/control conventions.
- Use the BEAM experiment design and current Cell Ranger documentation rather than an antibody catalog.
- Confirm that the selected 5′ immune-profiling chemistry supports the BEAM workflow, and use the experiment-specific reference supplied for that assay.

## Mixed references

A Feature Reference can contain more than one compatible feature class, but every class must have a matching library row and all required class-specific columns. Mixed references are validated conservatively. Prefer separate, explicit FASTQ library rows over relabeling one library after the fact.

## Broad catalog mode

An unused exact barcode normally produces zero or background-level counts. However, Cell Ranger permits one-base barcode correction, and a broad catalog can introduce ambiguity or plausible-looking low-count features. Catalog mode is useful for discovery when the exact panel is unavailable; the final interpretation should still be confirmed against reagent records.
