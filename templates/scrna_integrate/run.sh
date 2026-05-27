#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${script_dir}/run.py"

rm -rf "${script_dir}/.pixi"
rm -rf "${script_dir}/__pycache__"

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"
