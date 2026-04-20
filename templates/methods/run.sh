#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
derived_project_dir="${script_dir}"
if [[ "${script_dir}" == */.linkar/runs/* ]]; then
  derived_project_dir="$(cd "${script_dir}/../../.." && pwd)"
else
  derived_project_dir="$(cd "${script_dir}/.." && pwd)"
fi

if [[ -n "${PROJECT_DIR:-}" && -f "${PROJECT_DIR}/project.yaml" ]]; then
  project_dir="${PROJECT_DIR}"
else
  project_dir="${derived_project_dir}"
fi

exec python3 "${script_dir}/run.py" \
  --results-dir "${LINKAR_RESULTS_DIR}" \
  --project-dir "${project_dir}" \
  --style "${STYLE:-publication}" \
  --metadata-api-url "${METADATA_API_URL:-}" \
  --use-llm "${USE_LLM:-true}" \
  --llm-config "${LLM_CONFIG:-}" \
  --llm-base-url "${LLM_BASE_URL:-}" \
  --llm-model "${LLM_MODEL:-}" \
  --llm-temperature "${LLM_TEMPERATURE:-0.2}"
