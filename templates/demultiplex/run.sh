#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REPO_DEFAULT="https://github.com/MoSafi2/demultiplexing_prefect"
UPSTREAM_REVISION_DEFAULT="940067c3efd02cf3ac44707fc490d5e16fa8a01e"
CLONE_DIRNAME="demultiplexing_prefect"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

nonempty() {
  local value="${1:-}"
  if [[ -n "${value// }" ]]; then
    printf '%s\n' "${value}"
    return 0
  fi
  return 1
}

MODE="${MODE:?}"
QC_TOOL="${QC_TOOL:?}"
THREADS="${THREADS:-4}"
RUN_NAME="${RUN_NAME:-}"
BCL_DIR="${BCL_DIR:-}"
SAMPLESHEET="${SAMPLESHEET:-}"
USE_API_SAMPLESHEET="${USE_API_SAMPLESHEET:-true}"
AGENDO_ID="${AGENDO_ID:-}"
FLOWCELL_ID="${FLOWCELL_ID:-}"
MANIFEST_TSV="${MANIFEST_TSV:-}"
IN_FASTQ_DIR="${IN_FASTQ_DIR:-}"
CONTAMINATION_TOOL="${CONTAMINATION_TOOL:-none}"
KRAKEN_DB="${KRAKEN_DB:-}"
BRACKEN_DB="${BRACKEN_DB:-}"
FASTQ_SCREEN_CONF="${FASTQ_SCREEN_CONF:-}"
LINKAR_OUTPUT_DIR="${LINKAR_OUTPUT_DIR:?}"
LINKAR_RESULTS_DIR="${LINKAR_RESULTS_DIR:?}"

repo_ref="$(nonempty "${DEMULTIPLEXING_PREFECT_REPO:-}" || true)"
revision="$(nonempty "${DEMULTIPLEXING_PREFECT_REVISION:-}" || true)"
repo_ref="${repo_ref:-${UPSTREAM_REPO_DEFAULT}}"
revision="${revision:-${UPSTREAM_REVISION_DEFAULT}}"

repo_dir="${LINKAR_OUTPUT_DIR}/${CLONE_DIRNAME}"
if [[ ! -d "${repo_dir}" ]]; then
  git clone "${repo_ref}" "${repo_dir}"
  git -C "${repo_dir}" checkout "${revision}"
fi

effective_samplesheet="${SAMPLESHEET}"
if [[ "${MODE}" == "demux" ]] && ! nonempty "${effective_samplesheet}" >/dev/null; then
  if [[ "${USE_API_SAMPLESHEET}" == "true" ]]; then
    fetched_samplesheet="${LINKAR_OUTPUT_DIR}/samplesheet.csv"
    python "${SCRIPT_DIR}/fetch_samplesheet.py" \
      --bcl-dir "${BCL_DIR}" \
      --out "${fetched_samplesheet}" \
      --agendo-id "${AGENDO_ID}" \
      --flowcell-id "${FLOWCELL_ID}"
    if [[ -f "${fetched_samplesheet}" ]]; then
      effective_samplesheet="${fetched_samplesheet}"
    fi
  fi
fi

cd "${repo_dir}"

pixi run python cli.py \
  --mode "${MODE}" \
  --qc-tool "${QC_TOOL}" \
  --threads "${THREADS}" \
  --outdir "${LINKAR_RESULTS_DIR}" \
  --run-name "${RUN_NAME}" \
  --bcl_dir "${BCL_DIR}" \
  --samplesheet "${effective_samplesheet}" \
  --manifest-tsv "${MANIFEST_TSV}" \
  --in-fastq-dir "${IN_FASTQ_DIR}" \
  --contamination-tool "${CONTAMINATION_TOOL}" \
  --kraken-db "${KRAKEN_DB}" \
  --bracken-db "${BRACKEN_DB}" \
  --fastq-screen-conf "${FASTQ_SCREEN_CONF}"
