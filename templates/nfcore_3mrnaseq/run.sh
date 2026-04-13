#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${GENOME:-}" || "${GENOME}" == "__EDIT_ME_GENOME__" ]]; then
  echo "[error] genome is unresolved. Edit run.sh and replace __EDIT_ME_GENOME__ with a supported genome before running." >&2
  exit 2
fi

effective_genome="${GENOME}"
if [[ -n "${SPIKEIN:-}" && "${SPIKEIN}" == *ERCC* ]]; then
  effective_genome="${effective_genome}_with_ERCC"
fi

echo "[info] $(date) nf-core/rnaseq profile=docker genome=${effective_genome}"
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
            "name": "nf-core/rnaseq",
            "version": "3.22.2",
            "source": "static",
        },
        {
            "name": "execution_profile",
            "version": "docker",
            "source": "static",
        },
        {
            "name": "genome",
            "version": "${effective_genome}",
            "source": "param",
        },
    ]
}
path = Path("${LINKAR_RESULTS_DIR}") / "software_versions.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY

nextflow_args=(
  run nf-core/rnaseq
  -r 3.22.2
  -profile docker
  -c nextflow.config
  --input "${SAMPLESHEET:?}"
  --outdir "${LINKAR_RESULTS_DIR}"
  --extra_salmon_quant_args=--noLengthCorrection
  --extra_star_align_args=--alignIntronMax\ 1000000\ --alignIntronMin\ 20\ --alignMatesGapMax\ 1000000\ --alignSJoverhangMin\ 8\ --outFilterMismatchNmax\ 999\ --outFilterMultimapNmax\ 20\ --outFilterType\ BySJout\ --outFilterMismatchNoverLmax\ 0.1\ --clip3pAdapterSeq\ AAAAAAAA
  --genome "${effective_genome}"
  --igenomes_ignore true
  --igenomes_base /data/shared/igenomes/
  --gencode
  --featurecounts_group_type gene_type
)

if [[ -n "${MAX_CPUS:-}" ]]; then
  nextflow_args+=(--max_cpus "${MAX_CPUS}")
fi

if [[ -n "${MAX_MEMORY:-}" ]]; then
  nextflow_args+=(--max_memory "${MAX_MEMORY}")
fi

if [[ "${UMI:-}" == "UMI Second Strand SynthesisModule for QuantSeq FWD" ]]; then
  nextflow_args+=(
    --with_umi
    --umitools_extract_method regex
    --umitools_bc_pattern "^(?P<umi_1>.{8})(?P<discard_1>.{6}).*"
  )
fi

nextflow "${nextflow_args[@]}"

run_name="$(grep -oP 'Run name:\s+\K\S+' .nextflow.log | tail -n 1 || true)"
if [[ -n "${run_name}" ]]; then
  nextflow clean "${run_name}" -f || true
fi
