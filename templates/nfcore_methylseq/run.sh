#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${GENOME:-}" || "${GENOME}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit run.sh and replace __EDIT_ME_GENOME__ with a supported genome before running." >&2
  exit 2
fi

project_title="${PROJECT_NAME:-}"
if [[ -z "${project_title}" ]]; then
  project_title="$(basename "${LINKAR_PROJECT_DIR:-$PWD}")"
fi

echo "[info] $(date) nf-core/methylseq profile=docker genome=${GENOME} rrbs=${RRBS:-true}"
nextflow -version || true
mkdir -p "${LINKAR_RESULTS_DIR}"

python3 - <<PY
import json
import subprocess
from pathlib import Path

completed = subprocess.run(["nextflow", "-version"], check=False, capture_output=True, text=True)
raw = "\\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
payload = {
    "software": [
        {
            "name": "nextflow",
            "version": raw.splitlines()[0] if raw else "",
            "raw": raw,
            "command": "nextflow -version",
            "source": "command",
            "returncode": completed.returncode,
        },
        {
            "name": "nf-core/methylseq",
            "version": "4.2.0",
            "source": "static",
        },
        {
            "name": "execution_profile",
            "version": "docker",
            "source": "static",
        },
        {
            "name": "genome",
            "version": "${GENOME}",
            "source": "param",
        },
        {
            "name": "rrbs",
            "version": "${RRBS:-true}",
            "source": "param",
        },
    ]
}
path = Path("${LINKAR_RESULTS_DIR}") / "software_versions.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY

nextflow_args=(
  run nf-core/methylseq
  -r 4.2.0
  -profile docker
  --input "${SAMPLESHEET:?}"
  --outdir "${LINKAR_RESULTS_DIR}"
  --genome "${GENOME}"
  --multiqc_title "${project_title}"
)

if [[ "${RRBS:-true}" == "true" ]]; then
  nextflow_args+=(--rrbs)
fi

if [[ -n "${MAX_CPUS:-}" ]]; then
  nextflow_args+=(--max_cpus "${MAX_CPUS}")
fi

if [[ -n "${MAX_MEMORY:-}" ]]; then
  nextflow_args+=(--max_memory "${MAX_MEMORY}")
fi

nextflow "${nextflow_args[@]}"

run_name="$(grep -oP 'Run name:\s+\K\S+' .nextflow.log | tail -n 1 || true)"
if [[ -n "${run_name}" ]]; then
  nextflow clean "${run_name}" -f || true
fi
