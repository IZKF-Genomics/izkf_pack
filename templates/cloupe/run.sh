#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
cd "${script_dir}"

say() {
  printf '[cloupe] %s\n' "$*"
}

say "starting Loupe Browser export"
say "workspace: ${script_dir}"

if command -v pixi >/dev/null 2>&1; then
  say "checking pixi environment"
  pixi install
  say "converting H5AD to cloupe"
  pixi run python run.py "$@"
else
  say "pixi was not found; using system python3"
  python3 run.py "$@"
fi

if [[ "${WRITE_SOFTWARE_VERSIONS:-0}" == "1" ]]; then
  versions_output="${SOFTWARE_VERSIONS_JSON:-${LINKAR_RESULTS_DIR:-${script_dir}/results}/software_versions.json}"
  mkdir -p "$(dirname "${versions_output}")"
  python3 "${pack_root}/functions/software_versions.py" \
    --spec "${script_dir}/software_versions_spec.yaml" \
    --output "${versions_output}"
  say "software versions: ${versions_output}"
fi

if [[ "${LINKAR_COLLECT:-0}" == "1" ]]; then
  linkar collect "${script_dir}"
fi

if [[ "${LINKAR_CLEAN:-0}" == "1" ]]; then
  linkar clean "${script_dir}" --yes
fi
