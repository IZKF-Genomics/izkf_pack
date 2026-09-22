#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stamp="${script_dir}/.pixi/envs/default/.linkar_bioc_data_installed.genomeinfodbdata-1.2.13"
timeout_seconds="${LINKAR_BIOC_DATA_TIMEOUT_SECONDS:-900}"
retries="${LINKAR_BIOC_DATA_RETRIES:-2}"
export PREFIX="${CONDA_PREFIX:?This task must run inside the Pixi environment}"

if [[ -f "${stamp}" ]]; then
  exit 0
fi

attempt=1
while (( attempt <= retries + 1 )); do
  echo "Installing Bioconductor data package genomeinfodbdata-1.2.13 (attempt ${attempt}/$((retries + 1)))..."
  if timeout "${timeout_seconds}" installBiocDataPackage.sh "genomeinfodbdata-1.2.13"; then
    touch "${stamp}"
    exit 0
  else
    status=$?
  fi
  if (( attempt > retries )); then
    echo "Failed to install genomeinfodbdata after $((retries + 1)) attempts." >&2
    exit "${status}"
  fi
  sleep "$((attempt * 10))"
  attempt=$((attempt + 1))
done
