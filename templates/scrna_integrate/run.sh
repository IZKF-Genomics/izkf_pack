#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${script_dir}/run.py"

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"

# Remove template-declared runtime artifacts.
linkar clean "${script_dir}" --yes
