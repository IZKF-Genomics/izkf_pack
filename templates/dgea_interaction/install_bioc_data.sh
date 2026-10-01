#!/usr/bin/env bash
set -euo pipefail

ENV_DIR="$(pixi info --json | python -c 'import json,sys; data=json.load(sys.stdin); print(data["environments_info"][0]["prefix"])')"
export PREFIX="$ENV_DIR"
export PATH="$ENV_DIR/bin:$PATH"

organism="${ORGANISM:-${LINKAR_DGEA_ORGANISM:-}}"
organism="$(printf '%s' "${organism}" | tr '[:upper:]' '[:lower:]')"

install_bioc_data_package() {
  local package="$1"
  local timeout_seconds="${LINKAR_BIOC_DATA_TIMEOUT_SECONDS:-900}"
  local retries="${LINKAR_BIOC_DATA_RETRIES:-2}"
  local attempt=1

  while (( attempt <= retries + 1 )); do
    echo "Installing Bioconductor data package ${package} (attempt ${attempt}/$((retries + 1)), timeout ${timeout_seconds}s)..."
    if timeout "${timeout_seconds}" installBiocDataPackage.sh "${package}"; then
      return 0
    fi

    local status=$?
    if (( status == 124 )); then
      echo "Bioconductor data package ${package} timed out after ${timeout_seconds}s." >&2
    else
      echo "Bioconductor data package ${package} failed with exit status ${status}." >&2
    fi

    if (( attempt > retries )); then
      cat >&2 <<EOF
Bioconductor data package installation failed for ${package} after $((retries + 1)) attempt(s).
This can happen when the Bioconductor data mirror is temporarily unavailable or stalls mid-download.
Retry later, check network access to the data URLs reported above, or use:
  LINKAR_BIOC_DATA_TIMEOUT_SECONDS=<seconds> LINKAR_BIOC_DATA_RETRIES=<count> ./run.sh
EOF
      return "${status}"
    fi

    sleep "$((attempt * 10))"
    attempt=$((attempt + 1))
  done
}

required_packages=(
  "genomeinfodbdata-1.2.13"
  "go.db-3.20.0"
)

case "${organism}" in
  hsapiens)
    required_packages+=("org.hs.eg.db-3.20.0")
    ;;
  mmusculus)
    required_packages+=("org.mm.eg.db-3.20.0")
    ;;
  sscrofa)
    required_packages+=("org.ss.eg.db-3.20.0")
    ;;
  rnorvegicus | drerio | ggallus | "")
    echo "No bundled organism-specific Bioconductor data package is configured for organism '${organism:-unset}'."
    ;;
  *)
    echo "No bundled organism-specific Bioconductor data package is configured for organism '${organism}'." >&2
    ;;
esac

for p in "${required_packages[@]}"; do
  stamp="${ENV_DIR}/.linkar_bioc_data_installed.${p}"
  if [[ -f "${stamp}" ]]; then
    echo "Bioconductor data package ${p} already installed for this Pixi environment."
    continue
  fi
  install_bioc_data_package "$p"
  touch "${stamp}"
done
