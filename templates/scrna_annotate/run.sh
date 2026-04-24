#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./run.sh
  ./run.sh --tier tier1
  ./run.sh --tier tier2
  ./run.sh --tier tier3
  ./run.sh --from tier1 --to tier3

Default behavior:
  Runs Tier 1 quick preview only.
EOF
}

tier_to_dir() {
  case "$1" in
    tier1) printf '%s\n' "tier1_quick_preview" ;;
    tier2) printf '%s\n' "tier2_refinement" ;;
    tier3) printf '%s\n' "tier3_formal_annotation" ;;
    *) return 1 ;;
  esac
}

run_tier() {
  local tier="$1"
  local dir
  dir="$(tier_to_dir "${tier}")" || {
    echo "Unknown tier: ${tier}" >&2
    exit 1
  }
  echo "Running ${tier} (${dir})"
  bash "${script_dir}/${dir}/run.sh"
}

refresh_overview() {
  (
    cd "${script_dir}"
    pixi install >/dev/null
    pixi run python "${script_dir}/generate_overview.py"
  )
}

default_tier="tier1"
tier=""
from_tier=""
to_tier=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier)
      tier="${2:-}"
      shift 2
      ;;
    --from)
      from_tier="${2:-}"
      shift 2
      ;;
    --to)
      to_tier="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -n "${tier}" && ( -n "${from_tier}" || -n "${to_tier}" ) ]]; then
  echo "Use either --tier or --from/--to, not both." >&2
  exit 1
fi

if [[ -n "${tier}" ]]; then
  run_tier "${tier}"
  refresh_overview
  exit 0
fi

if [[ -z "${from_tier}" && -z "${to_tier}" ]]; then
  run_tier "${default_tier}"
  refresh_overview
  exit 0
fi

if [[ -z "${from_tier}" || -z "${to_tier}" ]]; then
  echo "Both --from and --to must be provided together." >&2
  exit 1
fi

tiers=(tier1 tier2 tier3)
from_index=-1
to_index=-1
for idx in "${!tiers[@]}"; do
  if [[ "${tiers[$idx]}" == "${from_tier}" ]]; then
    from_index=$idx
  fi
  if [[ "${tiers[$idx]}" == "${to_tier}" ]]; then
    to_index=$idx
  fi
done

if [[ ${from_index} -lt 0 || ${to_index} -lt 0 || ${from_index} -gt ${to_index} ]]; then
  echo "Invalid --from/--to range: ${from_tier} -> ${to_tier}" >&2
  exit 1
fi

running=false
for current in "${tiers[@]}"; do
  if [[ "${current}" == "${from_tier}" ]]; then
    running=true
  fi
  if [[ "${running}" == true ]]; then
    run_tier "${current}"
  fi
  if [[ "${current}" == "${to_tier}" ]]; then
    running=false
    break
  fi
done

refresh_overview
