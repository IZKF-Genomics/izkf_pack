#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
LINKAR_RESULTS_DIR="${LINKAR_RESULTS_DIR:-./results}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${script_dir}/.cache}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-${script_dir}/.local/share}"
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
python3 ./build_dgea_inputs.py \
  --workspace-dir "." \
  --results-dir "${LINKAR_RESULTS_DIR}" \
  --salmon-dir "${SALMON_DIR:?}" \
  --samplesheet "${SAMPLESHEET:?}" \
  --organism "${ORGANISM:?}" \
  --application "${APPLICATION:-}" \
  --name "${NAME:-}" \
  --authors "${AUTHORS:-}" \
  --use-llm "${USE_LLM:-true}" \
  --llm-config "${LLM_CONFIG:-}" \
  --llm-base-url "${LLM_BASE_URL:-}" \
  --llm-model "${LLM_MODEL:-}" \
  --llm-temperature "${LLM_TEMPERATURE:-0.2}"

config_args=(--samplesheet "${SAMPLESHEET}" --salmon-dir "${SALMON_DIR}" --config config/analysis.yaml --samples-out config/samples.csv)
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
pixi install --frozen
pixi run install-bioc-data
pixi run python "${pack_root}/functions/software_versions.py" --spec "${script_dir}/software_versions_spec.yaml" --output "${LINKAR_RESULTS_DIR}/software_versions.json"
pixi run Rscript DGEA_constructor.R
pixi run python build_interpretation.py \
  --results-dir "${LINKAR_RESULTS_DIR}" \
  --config config/analysis.yaml \
  --use-llm "${USE_LLM:-true}" \
  --llm-config "${LLM_CONFIG:-}" \
  --llm-base-url "${LLM_BASE_URL:-}" \
  --llm-model "${LLM_MODEL:-}" \
  --llm-temperature "${LLM_TEMPERATURE:-0.2}"
pixi run python render_reports.py

if [[ -z "${LINKAR_INSTANCE_ID:-}" ]]; then
  linkar collect "${script_dir}" --project "${script_dir}/.."
fi
linkar clean "${script_dir}" --yes
