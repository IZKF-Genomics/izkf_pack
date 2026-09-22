#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
LINKAR_RESULTS_DIR="${LINKAR_RESULTS_DIR:-./results}"
mode="run"

case "${1:-}" in
  --configure|--validate)
    mode="${1#--}"
    shift
    ;;
esac
if [[ "$#" -gt 0 ]]; then
  echo "Usage: ./run.sh [--configure|--validate]" >&2
  exit 2
fi

cd "${script_dir}"
python3 ./build_mirna_inputs.py \
  --workspace-dir "." \
  --results-dir "${LINKAR_RESULTS_DIR}" \
  --counts-file "${COUNTS_FILE:?}" \
  --hairpin-counts-file "${HAIRPIN_COUNTS_FILE:-}" \
  --samplesheet "${SAMPLESHEET:?}" \
  --organism "${ORGANISM:?}" \
  --name "${NAME:-}" \
  --authors "${AUTHORS:-}"

config_args=(
  --samplesheet "${SAMPLESHEET}"
  --counts-file "${COUNTS_FILE}"
  --config config/analysis.yaml
  --samples-out config/samples.csv
)

if [[ "${mode}" == "configure" ]]; then
  python3 ./configure_analysis.py "${config_args[@]}" --configure
  exit 0
fi
if [[ "${mode}" == "validate" ]]; then
  python3 ./configure_analysis.py "${config_args[@]}" --validate
  exit 0
fi

python3 ./configure_analysis.py "${config_args[@]}" --auto-if-missing
python3 ./configure_analysis.py "${config_args[@]}" --validate
pixi install
pixi run install-bioc-data
pixi run python "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${LINKAR_RESULTS_DIR}/software_versions.json"
pixi run Rscript miRNA_constructor.R

if [[ -z "${LINKAR_INSTANCE_ID:-}" ]]; then
  linkar collect "${script_dir}" --project "${script_dir}/.."
fi
linkar clean "${script_dir}" --yes
