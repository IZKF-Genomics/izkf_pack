#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for arg in "$@"; do
  case "$arg" in
    -resume)
      export LINKAR_NEXTFLOW_RESUME=true
      ;;
    -h|--help)
      echo "Usage: bash run.sh [-resume]"
      exit 0
      ;;
    *)
      echo "[error] unsupported argument: ${arg}" >&2
      echo "Usage: bash run.sh [-resume]" >&2
      exit 2
      ;;
  esac
done

exec python3 "${script_dir}/run.py" --run-script "${script_dir}/resolved_run.sh"
