#!/usr/bin/env bash
set -euo pipefail

template_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${template_dir}"

tmp_root=""
if [[ -z "${LINKAR_RESULTS_DIR:-}" ]]; then
  tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/fastqc-test.XXXXXX")"
  export LINKAR_RESULTS_DIR="${tmp_root}/results"
fi

cleanup() {
  if [[ -n "${tmp_root}" && -d "${tmp_root}" ]]; then
    rm -rf "${tmp_root}"
  fi
}
trap cleanup EXIT

export LINKAR_TESTDATA_DIR="${LINKAR_TESTDATA_DIR:-${template_dir}/testdata}"
export INPUT="${INPUT:-${LINKAR_TESTDATA_DIR}/sample.fastq.gz}"
export SAMPLE_NAME="${SAMPLE_NAME:-test_sample}"
export THREADS="${THREADS:-2}"

mkdir -p "${LINKAR_RESULTS_DIR}"

./run.sh

test -f "${LINKAR_RESULTS_DIR}/fastqc/summary.txt"
test -f "${LINKAR_RESULTS_DIR}/fastqc/report.txt"
printf 'fastqc template test passed\n'
