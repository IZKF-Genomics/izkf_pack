#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
prepare_only=false
for arg in "$@"; do
  if [[ "${arg}" == "--prepare-only" ]]; then
    prepare_only=true
  fi
done

python3 "${script_dir}/run.py" execute \
  --workspace "${script_dir}" \
  --results-dir "${results_dir}" \
  "$@"

if [[ "${prepare_only}" == "false" ]] && command -v linkar >/dev/null 2>&1 && [[ -e "${script_dir}/.linkar/meta.json" || -d "${script_dir}/../.linkar/meta" ]]; then
  linkar collect "${script_dir}"
fi
