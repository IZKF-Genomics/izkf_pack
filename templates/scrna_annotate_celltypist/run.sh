#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
cd "${script_dir}"

say() {
  printf '[scrna_annotate_celltypist] %s\n' "$*"
}

say "starting CellTypist annotation"
say "workspace: ${script_dir}"
say "results: ${results_dir}"

if command -v pixi >/dev/null 2>&1; then
  say "checking pixi environment"
  pixi install
  say "running annotation"
  pixi run python run.py
else
  say "pixi was not found; using system python3"
  python3 run.py
fi

say "outputs:"
say "  ${results_dir}/annotation_result.json"
say "  ${results_dir}/adata.annotated.h5ad"
say "  ${results_dir}/report.html"
say "  ${results_dir}/tables/celltypist_predictions.csv"
say "  ${results_dir}/tables/celltypist_available_models.csv"
