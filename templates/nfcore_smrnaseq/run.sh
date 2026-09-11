#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

if [[ ! -f config/run_params.env || -n "${SAMPLESHEET:-}" || -n "${GENOME:-}" || -n "${LINKAR_RESULTS_DIR:-}" ]]; then
  python3 run.py --prepare
fi

# shellcheck disable=SC1091
source config/run_params.env

if [[ "${GENOME}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit config/run_params.env or rerender with --genome." >&2
  exit 1
fi

REFERENCE_ARGS=()
if [[ -n "${MIRTRACE_SPECIES}" ]]; then
  REFERENCE_ARGS+=(--mirtrace_species "${MIRTRACE_SPECIES}")
fi
if [[ "${SAVE_REFERENCE}" == "true" ]]; then
  REFERENCE_ARGS+=(--save_reference)
fi

UMI_ARGS=()
if [[ "${WITH_UMI}" == "true" ]]; then
  UMI_ARGS+=(--with_umi --umitools_extract_method "${UMITOOLS_EXTRACT_METHOD}")
  if [[ -n "${UMITOOLS_BC_PATTERN}" ]]; then
    UMI_ARGS+=(--umitools_bc_pattern "${UMITOOLS_BC_PATTERN}")
  fi
  UMI_ARGS+=(--skip_umi_extract_before_dedup "${SKIP_UMI_EXTRACT_BEFORE_DEDUP}")
fi

INTERMEDIATE_ARGS=()
if [[ "${SAVE_INTERMEDIATES}" == "true" ]]; then
  INTERMEDIATE_ARGS+=(--save_intermediates)
fi

pixi install

echo "[info] running nf-core/smrnaseq 2.4.1"

pixi run nextflow run nf-core/smrnaseq \
  -r 2.4.1 \
  -profile docker \
  -c nextflow.config \
  -c config/resources.config \
  -resume \
  --input samplesheet.csv \
  --outdir results \
  --genome "${GENOME}" \
  --igenomes_ignore true \
  --three_prime_adapter "${THREE_PRIME_ADAPTER}" \
  "${REFERENCE_ARGS[@]}" \
  "${UMI_ARGS[@]}" \
  "${INTERMEDIATE_ARGS[@]}"

if [[ -n "${LINKAR_PROJECT_DIR:-}" ]]; then
  linkar collect --project "${LINKAR_PROJECT_DIR}" "${script_dir}"
else
  linkar collect "${script_dir}"
fi

linkar clean "${script_dir}" --yes
