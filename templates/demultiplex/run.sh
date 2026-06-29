#!/usr/bin/env bash
set -euo pipefail

upstream_repo_url="https://github.com/MoSafi2/demultiplexing_prefect"
upstream_commit="72c1550bc7c2941dbb9993ee60e4ff9a18bd36d4"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
upstream_repo_dir="${script_dir}/demultiplexing_prefect"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
results_dir="${LINKAR_RESULTS_DIR:?}"
samplesheet_path="${SAMPLESHEET:?}"

if [[ "${samplesheet_path}" != /* ]]; then
  samplesheet_path="${script_dir}/${samplesheet_path#./}"
fi

if [[ "${results_dir}" != /* ]]; then
  results_dir="${script_dir}/${results_dir#./}"
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
  --command "demultiplexer=$(
    if [[ "${PLATFORM:?}" == "aviti" ]]; then
      printf '%s' 'bases2fastq --version'
    else
      printf '%s' 'bcl-convert --version'
    fi
  )" \
  --output "${results_dir}/software_versions.json"

pushd "${upstream_repo_dir}" >/dev/null
pixi run demux-pipeline \
  --outdir "${results_dir}" \
  --platform "${PLATFORM:?}" \
  --input-dir "${BCL_DIR:?}" \
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

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"

# Remove template-declared runtime artifacts.
linkar clean "${script_dir}" --yes
