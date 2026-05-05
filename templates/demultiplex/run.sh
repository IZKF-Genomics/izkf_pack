#!/usr/bin/env bash
set -euo pipefail

upstream_repo_url="https://github.com/chaochungkuo/demultiplexing_prefect"
upstream_commit="d0ab7e358abc3adfd7bfd5db731c280b90d1e9e9"
upstream_repo_dir="./demultiplexing_prefect"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
git -C "${upstream_repo_dir}" checkout "${upstream_commit}"

mkdir -p "${results_dir}"
export DEMUX_RESULTS_DIR="${results_dir}"
python3 - <<'PY'
from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path


def run_version_command(command: list[str]) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        return {
            "command": " ".join(shlex.quote(part) for part in command),
            "source": "command",
            "error": str(exc),
        }
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return {
        "version": output.splitlines()[0] if output else "",
        "raw": output,
        "command": " ".join(shlex.quote(part) for part in command),
        "source": "command",
        "returncode": completed.returncode,
    }


payload = {
    "software": [
        {"name": "bcl-convert", **run_version_command(["bcl-convert", "--version"])},
    ]
}
output_path = Path(os.environ["DEMUX_RESULTS_DIR"]) / "software_versions.json"
output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY

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
