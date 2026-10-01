# dgea_interaction

Paired gene-level RNA-seq analysis for two genotypes measured under Control, normal stimulation (SR), and AF-like stimulation. The default configuration answers seven connected questions: baseline genotype effect; SR response in WT and TTN; genotype modification of the SR response; AF-versus-SR response in WT and TTN; and genotype modification of the AF-specific response.

The interaction models are difference-in-differences tests. Response labels such as enhanced, reduced/blunted, target-specific, and opposite are assigned only after the corresponding interaction passes the configured FDR threshold. GO biological-process GSEA uses the full ranked statistic.

## Usage

Render through Linkar, or run the materialized workspace with environment variables:

```bash
SALMON_DIR=/path/to/star_salmon \
SAMPLESHEET=/path/to/samplesheet.csv \
ORGANISM=hsapiens \
APPLICATION=nfcore_3mrnaseq \
./run.sh
```

Run `./run.sh --configure` to regenerate the inferred metadata and seven default contrasts interactively, or `./run.sh --validate` to validate existing configuration.

LLM interpretation is optional. Configure `LINKAR_LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`, or provide `LLM_CONFIG`. Statistical analysis never depends on an LLM: missing or failed configuration produces a deterministic narrative. Prompt, structured evidence, response metadata, and final text are retained under `results/`.

Main outputs are a self-contained overview report, seven comparison reports, and one XLSX workbook per comparison. Each workbook contains complete statistics, FDR hits, effect-threshold hits, GO GSEA results, and interaction response classes where applicable. Tables and figures show gene symbols first, while stable gene IDs remain available for traceability. PNG figures are exported at 450 dpi with matching vector PDF and SVG files.
