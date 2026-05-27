#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
cd "${script_dir}"

say() {
  printf '[scrna_annotate_manual_markers] %s\n' "$*"
}

say "starting manual marker annotation"
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

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"

say "outputs:"
say "  ${results_dir}/annotation_result.json"
say "  ${results_dir}/adata.annotated.h5ad"
say "  ${results_dir}/report.html"
say "  ${results_dir}/tables/cluster_annotation_summary.csv"
say "  ${results_dir}/tables/manual_marker_scores.csv"
say "  ${results_dir}/tables/manual_marker_catalog.csv"

rm -rf "${script_dir}/.pixi"
rm -rf "${script_dir}/__pycache__"

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"
