#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
render_only=0
no_browser=0

for arg in "$@"; do
  case "${arg}" in
    --render-only) render_only=1 ;;
    --no-browser) no_browser=1 ;;
    *)
      printf '[scrna_annotate_audit] unknown argument: %s\n' "${arg}" >&2
      exit 2
      ;;
  esac
done

cd "${script_dir}"

say() {
  printf '[scrna_annotate_audit] %s\n' "$*"
}

say "starting annotation audit"
say "workspace: ${script_dir}"
say "results: ${results_dir}"

if command -v pixi >/dev/null 2>&1; then
  say "checking pixi environment"
  pixi install
  say "running audit"
  pixi run python run.py
else
  say "pixi was not found; using system python3"
  python3 run.py
fi

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"

say "outputs:"
say "  ${results_dir}/annotation_audit.json"
say "  ${results_dir}/annotation_audit_cards.json"
say "  ${results_dir}/adata.final_annotated.h5ad"
say "  ${results_dir}/report.html"
say "  ${results_dir}/tables/final_annotation_decisions_draft.csv"

if [[ "${render_only}" == "1" ]]; then
  say "render-only mode; temporary local API was not started"
  exit 0
fi

say "starting temporary local API on localhost"
say "use --render-only to skip the API"
if [[ "${no_browser}" != "1" ]] && command -v xdg-open >/dev/null 2>&1; then
  (
    sleep 2
    url_file="${results_dir}/.audit_server_url"
    if [[ -s "${url_file}" ]]; then
      xdg-open "$(cat "${url_file}")" >/dev/null 2>&1 || true
    fi
  ) &
fi

if command -v pixi >/dev/null 2>&1; then
  pixi run python audit_server.py --host 127.0.0.1 --port 0
else
  python3 audit_server.py --host 127.0.0.1 --port 0
fi
