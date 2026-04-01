# multiqc

`multiqc` is a minimal shell-based Linkar template that writes placeholder MultiQC outputs under `results/multiqc`.

## Parameters

- `input_dir` (required): directory to summarize
- `title` (default: `IZKF MultiQC Summary`): title written into the placeholder summary

## Outputs

- `results_dir`
- `multiqc_dir`
- `multiqc_summary`
- `multiqc_report`

## Test

```bash
cd /Users/jovesus/github/izkf_genomics_pack/templates/multiqc
bash test.sh
```

```bash
pixi run linkar test multiqc --pack /Users/jovesus/github/izkf_genomics_pack
```
