#!/usr/bin/env bash
set -euo pipefail

upstream_repo_url="https://github.com/MoSafi2/demultiplexing_prefect"
upstream_commit="8c2ebab05f9c49487cb01e226c77f27893f84d0b"
upstream_repo_dir="./demultiplexing_prefect"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
render_root="$(pwd)"
results_dir="${LINKAR_RESULTS_DIR:?}"
samplesheet_path="${SAMPLESHEET:?}"

if [[ "${samplesheet_path}" != /* ]]; then
  samplesheet_path="${render_root}/${samplesheet_path#./}"
fi

if [[ "${results_dir}" != /* ]]; then
  results_dir="${render_root}/${results_dir#./}"
fi

rm -rf "${upstream_repo_dir}"
git clone --depth 1 "${upstream_repo_url}" "${upstream_repo_dir}"
git -C "${upstream_repo_dir}" fetch --depth 1 origin "${upstream_commit}"
git -C "${upstream_repo_dir}" checkout "${upstream_commit}"

mkdir -p "${results_dir}"
export UPSTREAM_COMMIT="${upstream_commit}"
export UPSTREAM_REPO_URL="${upstream_repo_url}"
python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"

pushd "${upstream_repo_dir}" >/dev/null
pixi run demux-pipeline \
  --outdir "${results_dir}" \
  --bcl_dir "${BCL_DIR:?}" \
  --samplesheet "${samplesheet_path}" \
  --qc-tool "${QC_TOOL:?}" \
  --contamination-tool "${CONTAMINATION_TOOL:?}" \
  --threads "${THREADS:?}" \
  --output-contract-file "${results_dir}/template_outputs.json" \
  ${KRAKEN_DB:+--kraken-db "${KRAKEN_DB}"} \
  ${BRACKEN_DB:+--bracken-db "${BRACKEN_DB}"} \
  ${FASTQ_SCREEN_CONF:+--fastq-screen-conf "${FASTQ_SCREEN_CONF}"}
popd >/dev/null

if [[ -d "${results_dir}/output" ]]; then
  find "${results_dir}/output" -type d -exec chmod 775 {} +
fi

python3 "${script_dir}/build_project_views.py" --results-dir "${results_dir}"

rm -rf .pixi
