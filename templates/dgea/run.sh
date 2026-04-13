#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${LINKAR_RESULTS_DIR}"

python3 ./build_dgea_inputs.py \
  --workspace-dir "." \
  --results-dir "${LINKAR_RESULTS_DIR}" \
  --salmon-dir "${SALMON_DIR:?}" \
  --samplesheet "${SAMPLESHEET:?}" \
  --organism "${ORGANISM:?}" \
  --spikein "${SPIKEIN:-}" \
  --application "${APPLICATION:-}" \
  --name "${NAME:-}" \
  --authors "${AUTHORS:-}"

pixi install
pixi run install-bioc-data
pixi run Rscript DGEA_constructor.R

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
        version_entry("pixi", ["pixi", "--version"]),
        version_entry("quarto", ["quarto", "--version"]),
        version_entry("R", ["pixi", "run", "Rscript", "--version"]),
        {
            "name": "organism",
            "version": "${ORGANISM:?}",
            "source": "param",
        },
        {
            "name": "application",
            "version": "${APPLICATION:-}",
            "source": "param",
        },
    ]
}
path = Path("${LINKAR_RESULTS_DIR}") / "software_versions.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY
