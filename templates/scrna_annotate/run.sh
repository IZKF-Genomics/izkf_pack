#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
reports_dir="${script_dir}/reports"

cd "${script_dir}"

mkdir -p "${reports_dir}"

python3 "${script_dir}/run.py"

pixi install

pixi run python "${script_dir}/build_annotation_outputs.py"

pixi run quarto render "${script_dir}/00_annotation_overview.qmd" --to html --output-dir "${reports_dir}" --no-clean
pixi run quarto render "${script_dir}/01_celltypist.qmd" --to html --output-dir "${reports_dir}" --no-clean
pixi run quarto render "${script_dir}/02_scanvi.qmd" --to html --output-dir "${reports_dir}" --no-clean
pixi run quarto render "${script_dir}/03_decoupler_review.qmd" --to html --output-dir "${reports_dir}" --no-clean
pixi run quarto render "${script_dir}/04_scdeepsort.qmd" --to html --output-dir "${reports_dir}" --no-clean
pixi run quarto render "${script_dir}/05_scgpt.qmd" --to html --output-dir "${reports_dir}" --no-clean

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/assets/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"
