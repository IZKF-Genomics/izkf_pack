#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
cd "${script_dir}"

say() {
  printf '[cloupe] %s\n' "$*"
}

say "starting Loupe Browser export"
say "workspace: ${script_dir}"
say "results: ${results_dir}"

if command -v pixi >/dev/null 2>&1; then
  say "checking pixi environment"
  pixi install
  say "converting H5AD to cloupe"
  pixi run python run.py
else
  say "pixi was not found; using system python3"
  python3 run.py
fi

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"

say "outputs:"
say "  ${results_dir}/output.cloupe"
say "  ${results_dir}/cloupe_export.json"

rm -rf "${script_dir}/.pixi"
rm -rf "${script_dir}/__pycache__"

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"
