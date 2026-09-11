#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

if [[ ! -f config/run_params.env || -n "${SAMPLESHEET:-}" || -n "${GENOME:-}" || -n "${LINKAR_RESULTS_DIR:-}" ]]; then
  python3 run.py --prepare
fi

# shellcheck disable=SC1091
source config/run_params.env

# Defaults keep workspaces rendered with template 0.1.x runnable.
MIRNA_GTF="${MIRNA_GTF:-}"
MATURE="${MATURE:-}"
HAIRPIN="${HAIRPIN:-}"

reference_count=0
for reference_path in "${MIRNA_GTF}" "${MATURE}" "${HAIRPIN}"; do
  if [[ -n "${reference_path}" ]]; then
    ((reference_count += 1))
    if [[ ! -f "${reference_path}" ]]; then
      echo "[error] miRNA reference file does not exist: ${reference_path}" >&2
      exit 1
    fi
  fi
done
if [[ "${reference_count}" -ne 0 && "${reference_count}" -ne 3 ]]; then
  echo "[error] MIRNA_GTF, MATURE, and HAIRPIN must be set together" >&2
  exit 1
fi

if [[ "${GENOME}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit config/run_params.env or rerender with --genome." >&2
  exit 1
fi

REFERENCE_ARGS=()
if [[ -n "${MIRTRACE_SPECIES}" ]]; then
  REFERENCE_ARGS+=(--mirtrace_species "${MIRTRACE_SPECIES}")
fi
if [[ -n "${MIRNA_GTF}" ]]; then
  REFERENCE_ARGS+=(--mirna_gtf "${MIRNA_GTF}")
fi
if [[ -n "${MATURE}" ]]; then
  REFERENCE_ARGS+=(--mature "${MATURE}")
fi
if [[ -n "${HAIRPIN}" ]]; then
  REFERENCE_ARGS+=(--hairpin "${HAIRPIN}")
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
