#!/usr/bin/env bash
set -euo pipefail

template_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${template_dir}"

tmp_root=""
if [[ -z "${LINKAR_RESULTS_DIR:-}" ]]; then
  tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/multiqc-test.XXXXXX")"
  export LINKAR_RESULTS_DIR="${tmp_root}/results"
fi

cleanup() {
  if [[ -n "${tmp_root}" && -d "${tmp_root}" ]]; then
    rm -rf "${tmp_root}"
  fi
}
trap cleanup EXIT

export LINKAR_TESTDATA_DIR="${LINKAR_TESTDATA_DIR:-${template_dir}/testdata}"
export INPUT_DIR="${INPUT_DIR:-${LINKAR_TESTDATA_DIR}/input}"
export TITLE="${TITLE:-Test MultiQC}"

mkdir -p "${LINKAR_RESULTS_DIR}"

./run.sh

test -f "${LINKAR_RESULTS_DIR}/multiqc/summary.txt"
test -f "${LINKAR_RESULTS_DIR}/multiqc/report.txt"
printf 'multiqc template test passed\n'
