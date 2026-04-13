#!/usr/bin/env bash
set -euo pipefail

upstream_repo_url="https://github.com/MoSafi2/demultiplexing_prefect"
upstream_commit="08a77d8010bce28c26b3c71089256ed1ba6a145a"
upstream_repo_dir="./demultiplexing_prefect"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
render_root="$(pwd)"
results_dir="${LINKAR_RESULTS_DIR:?}"
samplesheet_path="${SAMPLESHEET:?}"

if [[ "${samplesheet_path}" != /* ]]; then
  samplesheet_path="${render_root}/${samplesheet_path#./}"
fi

rm -rf "${upstream_repo_dir}"
git clone --depth 1 "${upstream_repo_url}" "${upstream_repo_dir}"
git -C "${upstream_repo_dir}" checkout "${upstream_commit}"

export UPSTREAM_REPO_URL="${upstream_repo_url}"
export UPSTREAM_COMMIT="${upstream_commit}"
python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"

pushd "${upstream_repo_dir}" >/dev/null
pixi run python -m demux_pipeline.cli \
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

rm -rf .pixi
