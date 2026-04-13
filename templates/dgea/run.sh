#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"

mkdir -p "${LINKAR_RESULTS_DIR}"

python3 ./build_dgea_inputs.py \
  --workspace-dir "." \
  --results-dir "${LINKAR_RESULTS_DIR}" \
  --salmon-dir "${SALMON_DIR:?}" \
  --samplesheet "${SAMPLESHEET:?}" \
  --organism "${ORGANISM:?}" \
  --spikein "${SPIKEIN:-}" \
  --application "${APPLICATION:-}" \
  --name "${NAME:-}" \
  --authors "${AUTHORS:-}"

pixi install
pixi run install-bioc-data
pixi run Rscript DGEA_constructor.R

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${LINKAR_RESULTS_DIR}/software_versions.json"
