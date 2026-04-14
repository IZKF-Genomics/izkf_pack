#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pack_root="${LINKAR_PACK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"

if [[ -z "${GENOME:-}" || "${GENOME}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit run.sh and replace __EDIT_ME_GENOME__ with a supported genome before running." >&2
  exit 2
fi

project_title="${PROJECT_NAME:-}"
if [[ -z "${project_title}" ]]; then
  project_title="$(basename "${LINKAR_PROJECT_DIR:-$PWD}")"
fi

echo "[info] $(date) nf-core/methylseq profile=docker genome=${GENOME} rrbs=${RRBS:-true}"
mkdir -p "${LINKAR_RESULTS_DIR}"
pixi install
pixi run nextflow -version || true
export RRBS_VALUE="${RRBS:-true}"
python3 "${pack_root}/functions/software_versions.py" \
  --spec "${script_dir}/software_versions_spec.yaml" \
  --command "nextflow=pixi run nextflow -version" \
  --output "${LINKAR_RESULTS_DIR}/software_versions.json"

limits_config="${LINKAR_RESULTS_DIR}/resource_limits.config"
cp "${script_dir}/nextflow.config" "${limits_config}"

if [[ -n "${MAX_CPUS:-}" ]]; then
  python3 - <<'PY' "${limits_config}" "${MAX_CPUS}"
from __future__ import annotations
from pathlib import Path
import sys

path = Path(sys.argv[1])
cpus = str(int(sys.argv[2]))
text = path.read_text(encoding="utf-8")
text = text.replace("__EDIT_ME_MAX_CPUS__", cpus)
path.write_text(text, encoding="utf-8")
PY
else
  python3 - <<'PY' "${limits_config}"
from __future__ import annotations
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("cpus: __EDIT_ME_MAX_CPUS__,\n", "")
path.write_text(text, encoding="utf-8")
PY
fi

if [[ -n "${MAX_MEMORY:-}" ]]; then
  python3 - <<'PY' "${limits_config}" "${MAX_MEMORY}"
from __future__ import annotations
from pathlib import Path
import sys

path = Path(sys.argv[1])
memory = str(sys.argv[2]).strip()
if memory.upper().endswith("GB"):
  memory = f"{memory[:-2]}.GB"
text = path.read_text(encoding="utf-8")
text = text.replace("__EDIT_ME_MAX_MEMORY__", memory)
path.write_text(text, encoding="utf-8")
PY
else
  python3 - <<'PY' "${limits_config}"
from __future__ import annotations
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("    memory: '__EDIT_ME_MAX_MEMORY__'\n", "")
path.write_text(text, encoding="utf-8")
PY
fi

nextflow_args=(
  run nf-core/methylseq
  -r 4.2.0
  -profile docker
  -c "${limits_config}"
  --input "${SAMPLESHEET:?}"
  --outdir "${LINKAR_RESULTS_DIR}"
  --genome "${GENOME}"
  --multiqc_title "${project_title}"
)

if [[ "${RRBS:-true}" == "true" ]]; then
  nextflow_args+=(--rrbs)
fi

pixi run nextflow "${nextflow_args[@]}"

run_name="$(grep -oP 'Run name:\s+\K\S+' .nextflow.log | tail -n 1 || true)"
if [[ -n "${run_name}" ]]; then
  pixi run nextflow clean "${run_name}" -f || true
fi
