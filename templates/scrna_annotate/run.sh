#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
cd "${script_dir}"

mkdir -p "${results_dir}"

say() {
  printf '[scrna_annotate] %s\n' "$*"
}

say "starting provider-based annotation"
say "workspace: ${script_dir}"
say "results: ${results_dir}"
if [ -z "${TISSUE:-}" ]; then
  say "tissue: not provided; exploratory providers will run in context-light mode"
fi

if command -v pixi >/dev/null 2>&1; then
  say "checking pixi environment"
  pixi install
  say "running annotation providers"
  pixi run python "run.py"
else
  say "pixi was not found; using system python3"
  python3 "run.py"
fi

say "outputs:"
say "  ${results_dir}/dataset_profile.json"
say "  ${results_dir}/provider_index.json"
say "  ${results_dir}/providers/marker_based/annotation_result.json"
if [ -f "${results_dir}/providers/marker_based/report.html" ]; then
  say "  ${results_dir}/providers/marker_based/report.html"
else
  say "  ${results_dir}/providers/marker_based/report.qmd"
fi
say "review marker evidence before treating labels as final annotations"
