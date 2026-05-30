#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

if [[ ! -f config/run_params.env || -n "${SAMPLESHEET:-}" || -n "${GENOME:-}" || -n "${LINKAR_RESULTS_DIR:-}" ]]; then
  python3 run.py --prepare
fi

# shellcheck disable=SC1091
source config/run_params.env

if [[ "${EFFECTIVE_GENOME}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit config/run_params.env or rerender with --genome." >&2
  exit 1
fi

RESOURCE_ARGS=()
if [[ -n "${MAX_CPUS}" ]]; then
  RESOURCE_ARGS+=(--max_cpus "${MAX_CPUS}")
fi
if [[ -n "${MAX_MEMORY}" ]]; then
  RESOURCE_ARGS+=(--max_memory "${MAX_MEMORY}")
fi

UMI_ARGS=()
if [[ "${UMI}" == "UMI Second Strand SynthesisModule for QuantSeq FWD" ]]; then
  UMI_ARGS+=(
    --with_umi
    --umitools_extract_method regex
    --umitools_bc_pattern '^(?P<umi_1>.{8})(?P<discard_1>.{6}).*'
  )
fi

pixi install

echo "[info] running nf-core/rnaseq 3.26.0"

pixi run nextflow run nf-core/rnaseq \
  -r 3.26.0 \
  -profile docker \
  -c nextflow.config \
  --input samplesheet.csv \
  --outdir results \
  --extra_salmon_quant_args="--noLengthCorrection" \
  --extra_star_align_args="--alignIntronMax 1000000 --alignIntronMin 20 --alignMatesGapMax 1000000 --alignSJoverhangMin 8 --outFilterMismatchNmax 999 --outFilterMultimapNmax 20 --outFilterType BySJout --outFilterMismatchNoverLmax 0.1 --clip3pAdapterSeq AAAAAAAA" \
  --genome "${EFFECTIVE_GENOME}" \
  --igenomes_ignore true \
  --igenomes_base /data/shared/igenomes/ \
  --gencode \
  "${RESOURCE_ARGS[@]}" \
  "${UMI_ARGS[@]}"

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"

# Remove template-declared runtime artifacts.
linkar clean "${script_dir}" --yes
