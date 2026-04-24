#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

pixi install
pixi run python "${script_dir}/run.py"
