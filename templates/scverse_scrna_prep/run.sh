#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"
project_dir="${LINKAR_PROJECT_DIR:-$(cd "${script_dir}/.." && pwd)}"
results_dir="${LINKAR_RESULTS_DIR:-${script_dir}/results}"
reports_dir="${script_dir}/reports"

mkdir -p "${results_dir}" "${reports_dir}"

python3 "${script_dir}/build_scrna_prep_inputs.py" \
  --workspace-dir "${script_dir}" \
  --project-dir "${project_dir}" \
  --results-dir "${results_dir}" \
  --input-h5ad "${INPUT_H5AD:-}" \
  --input-matrix "${INPUT_MATRIX:-}" \
  --input-source-template "${INPUT_SOURCE_TEMPLATE:-}" \
  --ambient-correction-applied "${AMBIENT_CORRECTION_APPLIED:-false}" \
  --ambient-correction-method "${AMBIENT_CORRECTION_METHOD:-none}" \
  --input-format "${INPUT_FORMAT:-auto}" \
  --var-names "${VAR_NAMES:-gene_symbols}" \
  --sample-metadata "${SAMPLE_METADATA:-}" \
  --organism "${ORGANISM:-}" \
  --batch-key "${BATCH_KEY:-batch}" \
  --condition-key "${CONDITION_KEY:-condition}" \
  --sample-id-key "${SAMPLE_ID_KEY:-sample_id}" \
  --doublet-method "${DOUBLET_METHOD:-none}" \
  --filter-predicted-doublets "${FILTER_PREDICTED_DOUBLETS:-false}" \
  --qc-mode "${QC_MODE:-fixed}" \
  --qc-nmads "${QC_NMADS:-3.0}" \
  --min-genes "${MIN_GENES:-200}" \
  --min-cells "${MIN_CELLS:-3}" \
  --min-counts "${MIN_COUNTS:-500}" \
  --max-pct-counts-mt "${MAX_PCT_COUNTS_MT:-20.0}" \
  --max-pct-counts-ribo "${MAX_PCT_COUNTS_RIBO:-}" \
  --max-pct-counts-hb "${MAX_PCT_COUNTS_HB:-}" \
  --n-top-hvgs "${N_TOP_HVGS:-3000}" \
  --n-pcs "${N_PCS:-30}" \
  --n-neighbors "${N_NEIGHBORS:-15}" \
  --leiden-resolution "${LEIDEN_RESOLUTION:-}" \
  --resolution-grid "${RESOLUTION_GRID:-0.2,0.4,0.6,0.8,1.0,1.2}"

pixi install
pixi run quarto render 00_qc.qmd --to html --output-dir reports --no-clean

python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --output "${results_dir}/software_versions.json"
