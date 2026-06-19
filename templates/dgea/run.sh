#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
configure=false
LINKAR_RESULTS_DIR="${LINKAR_RESULTS_DIR:-./results}"
LINKAR_DGEA_ORGANISM="${ORGANISM:-}"
export LINKAR_DGEA_ORGANISM

if [[ "${1:-}" == "--configure" ]]; then
  configure=true
  shift
fi

if [[ "$#" -gt 0 ]]; then
  echo "Usage: ./run.sh [--configure]" >&2
  exit 2
fi

mkdir -p "${LINKAR_RESULTS_DIR}"

run_pixi_install() {
  local timeout_seconds="${LINKAR_PIXI_INSTALL_TIMEOUT_SECONDS:-1800}"
  local retries="${LINKAR_PIXI_INSTALL_RETRIES:-2}"
  local concurrent_downloads="${LINKAR_PIXI_CONCURRENT_DOWNLOADS:-8}"
  local attempt=1

  while (( attempt <= retries + 1 )); do
    echo "Installing Pixi environment from lockfile (attempt ${attempt}/$((retries + 1)), timeout ${timeout_seconds}s)..."
    if timeout "${timeout_seconds}" \
      pixi install \
        --frozen \
        --concurrent-downloads "${concurrent_downloads}"; then
      return 0
    fi

    local status=$?
    if (( status == 124 )); then
      echo "Pixi install timed out after ${timeout_seconds}s." >&2
    else
      echo "Pixi install failed with exit status ${status}." >&2
    fi

    if (( attempt > retries )); then
      cat >&2 <<EOF
Pixi environment installation failed after $((retries + 1)) attempt(s).
This is often caused by a transient conda mirror or package download outage.
Check network access to the locked channels in pixi.lock, or retry with:
  LINKAR_PIXI_INSTALL_TIMEOUT_SECONDS=<seconds> LINKAR_PIXI_INSTALL_RETRIES=<count> ./run.sh
EOF
      return "${status}"
    fi

    sleep "$((attempt * 10))"
    attempt=$((attempt + 1))
  done
}

python3 ./build_dgea_inputs.py \
  --workspace-dir "." \
  --results-dir "${LINKAR_RESULTS_DIR}" \
  --salmon-dir "${SALMON_DIR:?}" \
  --samplesheet "${SAMPLESHEET:?}" \
  --organism "${ORGANISM:?}" \
  --spikein "${SPIKEIN:-}" \
  --application "${APPLICATION:-}" \
  --name "${NAME:-}" \
  --authors "${AUTHORS:-}"

if [[ "${configure}" == true ]]; then
  run_pixi_install
  pixi run python ./configure_comparisons.py \
    --samplesheet "${SAMPLESHEET:?}" \
    --constructor "DGEA_constructor.R"
  exit 0
fi

run_pixi_install
pixi run install-bioc-data
pixi run Rscript DGEA_constructor.R

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${LINKAR_RESULTS_DIR}/software_versions.json"

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"

# Remove template-declared runtime artifacts.
linkar clean "${script_dir}" --yes
