#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${LINKAR_RESULTS_DIR}/fastqc"

cat > "${LINKAR_RESULTS_DIR}/fastqc/summary.txt" <<EOF
template=fastqc
input=${INPUT}
sample_name=${SAMPLE_NAME}
threads=${THREADS}
EOF

printf "Placeholder FastQC template completed for %s\n" "${SAMPLE_NAME}" > "${LINKAR_RESULTS_DIR}/fastqc/report.txt"
