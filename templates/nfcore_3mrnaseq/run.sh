#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"

if [[ -z "${GENOME:-}" || "${GENOME}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit run.sh and replace __EDIT_ME_GENOME__ with a supported genome before running." >&2
  exit 2
fi

effective_genome="${GENOME}"
if [[ -n "${SPIKEIN:-}" && "${SPIKEIN}" == *ERCC* ]]; then
  effective_genome="${effective_genome}_with_ERCC"
fi

echo "[info] $(date) nf-core/rnaseq profile=docker genome=${effective_genome}"
nextflow -version || true
mkdir -p "${LINKAR_RESULTS_DIR}"
export EFFECTIVE_GENOME="${effective_genome}"
python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${LINKAR_RESULTS_DIR}/software_versions.json"

nextflow_args=(
  run nf-core/rnaseq
  -r 3.22.2
  -profile docker
  -c nextflow.config
  --input "${SAMPLESHEET:?}"
  --outdir "${LINKAR_RESULTS_DIR}"
  --extra_salmon_quant_args=--noLengthCorrection
  --extra_star_align_args=--alignIntronMax\ 1000000\ --alignIntronMin\ 20\ --alignMatesGapMax\ 1000000\ --alignSJoverhangMin\ 8\ --outFilterMismatchNmax\ 999\ --outFilterMultimapNmax\ 20\ --outFilterType\ BySJout\ --outFilterMismatchNoverLmax\ 0.1\ --clip3pAdapterSeq\ AAAAAAAA
  --genome "${effective_genome}"
  --igenomes_ignore true
  --igenomes_base /data/shared/igenomes/
  --gencode
  --featurecounts_group_type gene_type
)

if [[ -n "${MAX_CPUS:-}" ]]; then
  nextflow_args+=(--max_cpus "${MAX_CPUS}")
fi

if [[ -n "${MAX_MEMORY:-}" ]]; then
  nextflow_args+=(--max_memory "${MAX_MEMORY}")
fi

if [[ "${UMI:-}" == "UMI Second Strand SynthesisModule for QuantSeq FWD" ]]; then
  nextflow_args+=(
    --with_umi
    --umitools_extract_method regex
    --umitools_bc_pattern "^(?P<umi_1>.{8})(?P<discard_1>.{6}).*"
  )
fi

nextflow "${nextflow_args[@]}"

run_name="$(grep -oP 'Run name:\s+\K\S+' .nextflow.log | tail -n 1 || true)"
if [[ -n "${run_name}" ]]; then
  nextflow clean "${run_name}" -f || true
fi
