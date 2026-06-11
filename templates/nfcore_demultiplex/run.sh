#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

NEXTFLOW_ARGS=()
for arg in "$@"; do
  case "$arg" in
    -resume)
      NEXTFLOW_ARGS+=("-resume")
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

if [[ ! -f config/run_params.env || -n "${RAW_RUN_DIR:-}" || -n "${FLOWCELL_SAMPLESHEET:-}" || -n "${LINKAR_RESULTS_DIR:-}" ]]; then
  python3 run.py --prepare
fi

# shellcheck disable=SC1091
source config/run_params.env

export RAW_RUN_DIR FLOWCELL_ID FLOWCELL_LANE MERGE_LANES PLATFORM DEMULTIPLEXER SKIP_TOOLS V1_SCHEMA REMOVE_SAMPLESHEET_ADAPTER PROJECT_MULTIQC ALLOW_EMPTY_FASTQ MAX_CPUS MAX_MEMORY DEMUX_CPUS FALCO_CPUS PACK_ROOT
export NXF_VER="${NXF_VER:-25.10.2}"

if [[ -z "${FLOWCELL_ID}" ]]; then
  echo "[error] flowcell id is unresolved. Edit config/run_params.env or rerender with --flowcell-id." >&2
  exit 1
fi

if [[ -z "${DEMULTIPLEXER}" ]]; then
  echo "[error] demultiplexer is unresolved. Edit config/run_params.env or rerender with --platform or --demultiplexer." >&2
  exit 1
fi

LANE_ARGS=()
if [[ -n "${FLOWCELL_LANE}" ]]; then
  LANE_ARGS+=(--flowcell_lane "${FLOWCELL_LANE}")
fi

SKIP_ARGS=()
if [[ -n "${SKIP_TOOLS}" ]]; then
  SKIP_ARGS+=(--skip_tools "${SKIP_TOOLS}")
fi

pixi install
export PATH="${script_dir}/.pixi/envs/default/bin:${PATH}"

echo "[info] running nf-core/demultiplex 1.7.1 with ${DEMULTIPLEXER}"
echo "[info] using Nextflow ${NXF_VER}"
echo "[info] resource cap: MAX_CPUS=${MAX_CPUS:-unset}, MAX_MEMORY=${MAX_MEMORY:-unset}, DEMUX_CPUS=${DEMUX_CPUS:-auto}, FALCO_CPUS=${FALCO_CPUS:-auto}"
python3 check_manifest.py \
  --flowcell-samplesheet flowcell_samplesheet.csv \
  --output results/manifest_lint_report.csv

python3 check_empty_fastqs.py \
  --results-dir results \
  --work-dir results \
  --flowcell-samplesheet flowcell_samplesheet.csv \
  --output results/empty_fastq_report.csv

set +e
pixi run nextflow run nf-core/demultiplex \
  -r 1.7.1 \
  -profile docker \
  -c nextflow.config \
  --flowcell_id "${FLOWCELL_ID}" \
  --flowcell_samplesheet flowcell_samplesheet.csv \
  --flowcell_path "${RAW_RUN_DIR}" \
  --outdir results \
  --demultiplexer "${DEMULTIPLEXER}" \
  --trim_fastq false \
  --remove_samplesheet_adapter "${REMOVE_SAMPLESHEET_ADAPTER}" \
  --v1_schema "${V1_SCHEMA}" \
  --multiqc_title "${FLOWCELL_ID}" \
  "${LANE_ARGS[@]}" \
  "${SKIP_ARGS[@]}" \
  "${NEXTFLOW_ARGS[@]}"
nextflow_status=$?
set -e

if [[ "${nextflow_status}" -ne 0 ]]; then
  if [[ -f .nextflow.log ]] && grep -q "Pipeline completed successfully" .nextflow.log && grep -Eq "UnixPath\\.rightShift\\(\\)|rightShift.*UnixPath|Unknown method invocation.*rightShift" .nextflow.log; then
    echo "[error] nf-core output publishing hit a Nextflow/Groovy compatibility issue." >&2
    echo "[error] Keep NXF_VER pinned to 25.10.2, or rerun with: NXF_VER=25.10.2 bash run.sh -resume" >&2
    echo "[info] recovering demultiplexed FASTQs from successful work directories"
    python3 recover_demultiplex_fastqs.py \
      --results-dir results \
      --work-dir work \
      --flowcell-id "${FLOWCELL_ID}" \
      --demultiplexer "${DEMULTIPLEXER}"
  else
    echo "[error] nf-core/demultiplex exited with status ${nextflow_status}." >&2
    if [[ -f .nextflow.log ]] && grep -q "startsWith() on null object" .nextflow.log; then
      echo "[error] nf-core likely attempted to read an empty FASTQ while generating read-group metadata." >&2
    fi
    python3 check_empty_fastqs.py \
      --results-dir results \
      --work-dir work \
      --flowcell-samplesheet flowcell_samplesheet.csv \
      --output results/empty_fastq_report.csv \
      --fail-on-empty || true
    echo "[error] If empty FASTQs are listed, fix/comment the affected rows in flowcell_samplesheet.csv and rerun with -resume." >&2
    exit "${nextflow_status}"
  fi
fi

if [[ "${ALLOW_EMPTY_FASTQ}" == "true" ]]; then
  python3 check_empty_fastqs.py \
    --results-dir results \
    --work-dir results \
    --flowcell-samplesheet flowcell_samplesheet.csv \
    --output results/empty_fastq_report.csv
else
  python3 check_empty_fastqs.py \
    --results-dir results \
    --work-dir results \
    --flowcell-samplesheet flowcell_samplesheet.csv \
    --output results/empty_fastq_report.csv \
    --fail-on-empty
fi

python3 build_project_views.py \
  --results-dir results \
  --flowcell-samplesheet flowcell_samplesheet.csv \
  --project-multiqc "${PROJECT_MULTIQC}" \
  --allow-empty-fastq "${ALLOW_EMPTY_FASTQ}"

flowcell_results_dir="results/${FLOWCELL_ID}"
if [[ -d "${flowcell_results_dir}" ]]; then
  rm -rf -- "${flowcell_results_dir}"
  echo "[info] removed nf-core flowcell-level output folder: ${flowcell_results_dir}"
fi

python3 "${PACK_ROOT}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${script_dir}/results/software_versions.json"

# Record outputs in Linkar after successful manual execution.
linkar collect "${script_dir}"

# Remove template-declared runtime artifacts.
linkar clean "${script_dir}" --yes
