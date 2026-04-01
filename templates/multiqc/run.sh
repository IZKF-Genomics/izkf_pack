#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${LINKAR_RESULTS_DIR}/multiqc"

cat > "${LINKAR_RESULTS_DIR}/multiqc/summary.txt" <<EOF
template=multiqc
input_dir=${INPUT_DIR}
title=${TITLE}
EOF

printf "Placeholder MultiQC template completed for %s\n" "${INPUT_DIR}" > "${LINKAR_RESULTS_DIR}/multiqc/report.txt"
