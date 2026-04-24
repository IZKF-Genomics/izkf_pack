#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
cd "${script_dir}"

python3 "run.py" --prepare-only
mkdir -p "${results_dir}" "reports"
pixi install
pixi run quarto render "scrna_prep.qmd" --to html --output-dir "reports" --no-clean
python3 "${pack_root}/functions/software_versions.py" \
  --spec "assets/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"
