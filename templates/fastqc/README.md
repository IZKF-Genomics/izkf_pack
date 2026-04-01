# fastqc

`fastqc` is a minimal shell-based Linkar template that writes placeholder FastQC outputs under `results/fastqc`.

## Parameters

- `input` (required): input FASTQ path
- `sample_name` (default: `sample`): label written into the placeholder report
- `threads` (default: `4`): placeholder thread count written into the summary

## Outputs

- `results_dir`
- `fastqc_dir`
- `fastqc_summary`
- `fastqc_report`

## Test

```bash
cd /Users/jovesus/github/izkf_genomics_pack/templates/fastqc
bash test.sh
```

```bash
pixi run linkar test fastqc --pack /Users/jovesus/github/izkf_genomics_pack
```
