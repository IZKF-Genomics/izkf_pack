# nfcore_smrnaseq

Facility wrapper for [`nf-core/smrnaseq`](https://nf-co.re/smrnaseq), pinned to
pipeline release `2.4.1`. The rendered workspace is intentionally editable:
`run.py` prepares the input and parameter file, while `run.sh` shows the exact
Nextflow command.

## Typical use

From a Linkar project containing completed `nfcore_demultiplex` or legacy
`demultiplex` outputs:

```bash
linkar render nfcore_smrnaseq \
  --genome Sscrofa11.1 \
  --mirna-gtf /path/to/ssc.gff3 \
  --mature /path/to/ssc_mature.fa \
  --hairpin /path/to/ssc_hairpin.fa
cd nfcore_smrnaseq
bash run.sh
```

With `--binding default`, Linkar generates `samplesheet.csv` from the curated
`demux_fastq_files` recorded in `project.yaml`. Only those recorded FASTQs are
included; `Undetermined` and `Unassigned` files are excluded. Both single-end
and paired-end inputs are supported.

The template uses Docker, enables Nextflow `-resume`, and writes the resolved
`max_cpus` and `max_memory` values to `config/resources.config` as native
Nextflow per-process ceilings. The default binding resolves both to 80 percent
of detectable host resources. Generated reference files are saved by default
because facility genomes may not yet provide a reusable Bowtie 1 index.
Nextflow is constrained to `>=24.04.2,<26` because pipeline `2.4.1` is not
compatible with the Nextflow 26 parser.

## Scientific parameters

- Confirm `three_prime_adapter` against the small-RNA library kit. The default
  is the nf-core/smrnaseq Illumina adapter value.
- `mirtrace_species` is derived from supported facility genome names unless it
  is overridden; for `Sscrofa11.1`, it is `ssc`.
- For species whose current miRBase download does not provide a genome GFF3,
  set `mirna_gtf`, `mature`, and `hairpin` together to local files from one
  database release. Do not mix coordinate and sequence identifiers from
  different databases. This is required for the `Sscrofa11.1` pig example.
- Enable `with_umi` only for UMI-bearing libraries and provide the correct
  `umitools_extract_method` and `umitools_bc_pattern` for that kit.
- `save_intermediates` is off by default to limit disk use.

## Main outputs

- `results/multiqc/multiqc_report.html`
- `results/mirna_quant/mirtop/mirna.tsv`
- `results/mirna_quant/mirtop/joined_samples_mirtop.tsv`
- `results/mirna_quant/edger_qc/`
- `results/mirdeep2/`
- `results/mirtrace/`
- `results/pipeline_info/`

The pipeline run starts only when `bash run.sh` is executed. Rendering alone is
safe for checking the samplesheet, genome, adapter, UMI options, resources, and
final command.
