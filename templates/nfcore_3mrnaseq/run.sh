#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${script_dir}/run.py" --run-script "${script_dir}/resolved_run.sh"

rm -rf "${script_dir}/.pixi"
rm -rf "${script_dir}/work" "${script_dir}/.nextflow" "${script_dir}/.nextflow.log"*

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"
