#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${script_dir}/run.py"

# Record outputs in Linkar after successful manual execution.
if [[ -n "${LINKAR_PROJECT_DIR:-}" ]]; then
  linkar collect --project "${LINKAR_PROJECT_DIR}" "${script_dir}"
else
  linkar collect "${script_dir}"
fi

# Remove template-declared runtime artifacts.
linkar clean "${script_dir}" --yes
