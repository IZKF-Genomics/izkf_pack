#!/usr/bin/env bash
set -euo pipefail

upstream_repo_url="https://github.com/MoSafi2/demultiplexing_prefect"
upstream_commit="08a77d8010bce28c26b3c71089256ed1ba6a145a"
upstream_repo_dir="./demultiplexing_prefect"

render_root="$(pwd)"
results_dir="${LINKAR_RESULTS_DIR:?}"
samplesheet_path="${SAMPLESHEET:?}"

if [[ "${samplesheet_path}" != /* ]]; then
  samplesheet_path="${render_root}/${samplesheet_path#./}"
fi

rm -rf "${upstream_repo_dir}"
git clone --depth 1 "${upstream_repo_url}" "${upstream_repo_dir}"
git -C "${upstream_repo_dir}" checkout "${upstream_commit}"

python3 - <<PY
import json
import subprocess
from pathlib import Path


def version_entry(name, command):
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    raw = "\\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    return {
        "name": name,
        "version": raw.splitlines()[0] if raw else "",
        "raw": raw,
        "command": " ".join(command),
        "source": "command",
        "returncode": completed.returncode,
    }


payload = {
    "software": [
        version_entry("bcl-convert", ["bcl-convert", "--version"]),
        version_entry("pixi", ["pixi", "--version"]),
        {
            "name": "demultiplexing_prefect",
            "version": "${upstream_commit}",
            "repository": "${upstream_repo_url}",
            "source": "static",
        },
        {
            "name": "qc_tool",
            "version": "${QC_TOOL:?}",
            "source": "param",
        },
        {
            "name": "contamination_tool",
            "version": "${CONTAMINATION_TOOL:?}",
            "source": "param",
        },
    ]
}
path = Path("${results_dir}") / "software_versions.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY

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
