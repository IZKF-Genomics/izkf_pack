#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"

if [[ -z "${GENOME:-}" || "${GENOME}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit run.sh and replace __EDIT_ME_GENOME__ with a supported genome before running." >&2
  exit 2
fi

project_title="${PROJECT_NAME:-}"
if [[ -z "${project_title}" ]]; then
  project_title="$(basename "${LINKAR_PROJECT_DIR:-$PWD}")"
fi

echo "[info] $(date) nf-core/methylseq profile=docker genome=${GENOME} rrbs=${RRBS:-true}"
nextflow -version || true
mkdir -p "${LINKAR_RESULTS_DIR}"
export RRBS_VALUE="${RRBS:-true}"
python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${LINKAR_RESULTS_DIR}/software_versions.json"

nextflow_args=(
  run nf-core/methylseq
  -r 4.2.0
  -profile docker
  --input "${SAMPLESHEET:?}"
  --outdir "${LINKAR_RESULTS_DIR}"
  --genome "${GENOME}"
  --multiqc_title "${project_title}"
)

if [[ "${RRBS:-true}" == "true" ]]; then
  nextflow_args+=(--rrbs)
fi

if [[ -n "${MAX_CPUS:-}" ]]; then
  nextflow_args+=(--max_cpus "${MAX_CPUS}")
fi

if [[ -n "${MAX_MEMORY:-}" ]]; then
  nextflow_args+=(--max_memory "${MAX_MEMORY}")
fi

nextflow "${nextflow_args[@]}"

run_name="$(grep -oP 'Run name:\s+\K\S+' .nextflow.log | tail -n 1 || true)"
if [[ -n "${run_name}" ]]; then
  nextflow clean "${run_name}" -f || true
fi
