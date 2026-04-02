#!/usr/bin/env bash
set -euo pipefail

results_dir="${1:?results_dir is required}"
samplesheet="${2:?samplesheet is required}"
genome="${3:?genome is required}"
umi="${4:-}"
spikein="${5:-}"
max_cpus="${6:-}"
max_memory="${7:-}"

if [[ -z "${genome}" || "${genome}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit run.sh and replace __EDIT_ME_GENOME__ with a supported genome before running." >&2
  exit 2
fi

if [[ -n "${spikein}" && "${spikein}" == *ERCC* ]]; then
  genome="${genome}_with_ERCC"
fi

echo "[info] $(date) nf-core/rnaseq profile=docker genome=${genome}"
nextflow -version || true
mkdir -p "${results_dir}"

args=(
  run
  nf-core/rnaseq
  -r
  "3.22.2"
  -profile
  "docker"
  -c
  "nextflow.config"
  --input
  "${samplesheet}"
  --outdir
  "${results_dir}"
  --extra_salmon_quant_args=--noLengthCorrection
  --extra_star_align_args=--alignIntronMax\ 1000000\ --alignIntronMin\ 20\ --alignMatesGapMax\ 1000000\ --alignSJoverhangMin\ 8\ --outFilterMismatchNmax\ 999\ --outFilterMultimapNmax\ 20\ --outFilterType\ BySJout\ --outFilterMismatchNoverLmax\ 0.1\ --clip3pAdapterSeq\ AAAAAAAA
  --genome
  "${genome}"
  --igenomes_ignore
  true
  --igenomes_base
  "/data/shared/igenomes/"
  --gencode
  --featurecounts_group_type
  gene_type
)

if [[ -n "${max_cpus}" ]]; then
  args+=(--max_cpus "${max_cpus}")
fi
if [[ -n "${max_memory}" ]]; then
  args+=(--max_memory "${max_memory}")
fi
if [[ "${umi}" == "UMI Second Strand SynthesisModule for QuantSeq FWD" ]]; then
  args+=(
    --with_umi
    --umitools_extract_method
    regex
    --umitools_bc_pattern
    "^(?P<umi_1>.{8})(?P<discard_1>.{6}).*"
  )
fi

nextflow "${args[@]}"

run_name="$(grep -oP 'Run name:\s+\K\S+' .nextflow.log | tail -n 1 || true)"
if [[ -n "${run_name}" ]]; then
  nextflow clean "${run_name}" -f || true
fi
