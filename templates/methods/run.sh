#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "${script_dir}/run.py" \
  --results-dir "${LINKAR_RESULTS_DIR}" \
  --project-dir "${PROJECT_DIR:-..}" \
  --style "${STYLE:-publication}" \
  --use-llm "${USE_LLM:-false}" \
  --llm-config "${LLM_CONFIG:-}" \
  --llm-base-url "${LLM_BASE_URL:-}" \
  --llm-model "${LLM_MODEL:-}" \
  --llm-temperature "${LLM_TEMPERATURE:-0.2}"
