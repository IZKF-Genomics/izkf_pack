#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"

mkdir -p "${results_dir}"

python3 "${script_dir}/build_ercc_inputs.py" \
  --workspace-dir "${script_dir}" \
  --results-dir "${results_dir}" \
  --salmon-dir "${SALMON_DIR:?}" \
  --samplesheet "${SAMPLESHEET:?}" \
  --authors "${AUTHORS:-}"

pixi install
pixi run quarto render ERCC.runtime.qmd --to html --output-dir "${results_dir}" --output ERCC.html --no-clean

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"
