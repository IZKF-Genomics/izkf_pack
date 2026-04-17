#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
project_dir="${LINKAR_PROJECT_DIR:-$(cd "${script_dir}/.." && pwd)}"
pixi_prefix="${script_dir}/.pixi/envs/default"

mkdir -p "${LINKAR_RESULTS_DIR:-${script_dir}/results}"

python3 "${script_dir}/build_dnam_inputs.py" \
  --workspace-dir "${script_dir}" \
  --project-dir "${project_dir}" \
  --results-dir "${LINKAR_RESULTS_DIR:-${script_dir}/results}" \
  --authors "${AUTHORS:-}"

pixi install

bootstrap_stamp="${pixi_prefix}/.dnam_bioc_bootstrap_v2"
required_pkg_names=()
required_pkg_scripts=()

add_required_bioc_data_pkg() {
  required_pkg_names+=("$1")
  required_pkg_scripts+=("$2")
}

pkg_dir_exists() {
  local pkg="$1"
  [[ -d "${pixi_prefix}/lib/R/library/${pkg}" ]] && [[ -n "$(find "${pixi_prefix}/lib/R/library/${pkg}" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]
}

pkg_lock_path() {
  local pkg="$1"
  printf '%s/lib/R/library/00LOCK-%s' "${pixi_prefix}" "${pkg}"
}

ensure_bioc_data_pkg() {
  local pkg="$1"
  local post_link_script="$2"
  local script_path="${pixi_prefix}/bin/${post_link_script}"
  local lock_dir
  lock_dir="$(pkg_lock_path "${pkg}")"
  if pkg_dir_exists "${pkg}"; then
    return 0
  fi
  if [[ -d "${lock_dir}" ]]; then
    rm -rf "${lock_dir}"
  fi
  if [[ ! -x "${script_path}" ]]; then
    echo "Missing post-link helper for ${pkg}: ${script_path}" >&2
    exit 1
  fi
  PATH="${pixi_prefix}/bin:${PATH}" PREFIX="${pixi_prefix}" "${script_path}"
  if ! pkg_dir_exists "${pkg}"; then
    echo "Failed to provision required R package ${pkg}" >&2
    exit 1
  fi
}

enabled_arrays="$(
  python3 - <<'PY'
from pathlib import Path
import tomllib

cfg = tomllib.loads(Path("config/datasets.toml").read_text())
arrays = []
for ds in cfg.get("datasets", []):
    if ds.get("enabled", True):
        arrays.append(str(ds.get("array_type", "AUTO")).strip().upper())
print(",".join(arrays))
PY
)"

add_required_bioc_data_pkg "GenomeInfoDbData" ".bioconductor-genomeinfodbdata-post-link.sh"
add_required_bioc_data_pkg "GO.db" ".bioconductor-go.db-post-link.sh"
add_required_bioc_data_pkg "org.Hs.eg.db" ".bioconductor-org.hs.eg.db-post-link.sh"

if [[ "${enabled_arrays}" == *"450K"* ]] || [[ "${enabled_arrays}" == *"AUTO"* ]]; then
  add_required_bioc_data_pkg "IlluminaHumanMethylation450kmanifest" ".bioconductor-illuminahumanmethylation450kmanifest-post-link.sh"
  add_required_bioc_data_pkg "IlluminaHumanMethylation450kanno.ilmn12.hg19" ".bioconductor-illuminahumanmethylation450kanno.ilmn12.hg19-post-link.sh"
fi

if [[ "${enabled_arrays}" == *"EPIC"* ]] || [[ "${enabled_arrays}" == *"AUTO"* ]] || [[ "${enabled_arrays}" == *"EPIC_V2"* ]] || [[ "${enabled_arrays}" == *"EPICV2"* ]]; then
  add_required_bioc_data_pkg "IlluminaHumanMethylationEPICmanifest" ".bioconductor-illuminahumanmethylationepicmanifest-post-link.sh"
  add_required_bioc_data_pkg "IlluminaHumanMethylationEPICanno.ilm10b4.hg19" ".bioconductor-illuminahumanmethylationepicanno.ilm10b4.hg19-post-link.sh"
  add_required_bioc_data_pkg "IlluminaHumanMethylationEPICv2manifest" ".bioconductor-illuminahumanmethylationepicv2manifest-post-link.sh"
  add_required_bioc_data_pkg "IlluminaHumanMethylationEPICv2anno.20a1.hg38" ".bioconductor-illuminahumanmethylationepicv2anno.20a1.hg38-post-link.sh"
fi

bootstrap_key="$(
  printf '%s\n' "${required_pkg_names[@]}" | sort
)"

if [[ ! -f "${bootstrap_stamp}" ]] || ! cmp -s <(printf '%s' "${bootstrap_key}") "${bootstrap_stamp}"; then
  for i in "${!required_pkg_names[@]}"; do
    ensure_bioc_data_pkg "${required_pkg_names[$i]}" "${required_pkg_scripts[$i]}"
  done
  printf '%s' "${bootstrap_key}" > "${bootstrap_stamp}"
fi

if [[ "${DNAM_FORCE_SYNC:-0}" == "1" ]]; then
  pixi run sync-samples
fi
pixi run preflight
pixi run analyze

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${LINKAR_RESULTS_DIR:-${script_dir}/results}/software_versions.json"
