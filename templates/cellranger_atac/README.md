# cellranger_atac

`cellranger_atac` discovers samples from a FASTQ directory, runs one
`cellranger-atac count` per sample, writes an `aggregation.csv`, and optionally
runs `cellranger-atac aggr` on the successful count outputs.

## Parameters

- `fastq_dir`: directory containing FASTQ files named like
  `SampleName_S1_L001_R1_001.fastq.gz`
- `reference`: Cell Ranger ATAC reference path
- `cellranger_atac_bin`: executable name or path, default `cellranger-atac`
- `run_aggr`: when true, run `aggr` if at least two samples are discovered
- `localcores`: optional pass-through for Cell Ranger local CPU allocation
- `localmem`: optional pass-through for Cell Ranger local memory allocation in GB

## Output layout

- `results/counts/<sample>/...`: one `count` output directory per sample
- `results/aggregation.csv`: generated ATAC aggregation CSV with
  `library_id,fragments,cells`
- `results/combined/...`: aggregated output from `cellranger-atac aggr`
- `results/samples.json`: manifest of discovered samples and output paths

## Sample discovery

The template scans only the top level of `fastq_dir` for `*.fastq.gz` and
extracts sample names using the Illumina-style prefix before `_S<digits>`.
Files that do not match that pattern are ignored.

## Example

```bash
linkar run cellranger_atac \
  --pack /home/ckuo/github/izkf_pack \
  --param fastq_dir=/results/output/260330_Yildiz_ZimmerBensch_BioII_scATAcseq \
  --param reference=/path/to/refdata-cellranger-atac-mm10-1.2.0
```

This will produce count runs such as:

```bash
cellranger-atac count --id=Ctrl_m --reference=... --fastqs=... --sample=Ctrl_m
cellranger-atac count --id=Ctrl_f --reference=... --fastqs=... --sample=Ctrl_f
cellranger-atac count --id=KO_m --reference=... --fastqs=... --sample=KO_m
cellranger-atac count --id=KO_f --reference=... --fastqs=... --sample=KO_f
cellranger-atac aggr --id=combined --csv=aggregation.csv --reference=...
```
