#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


FUNCTIONS_DIR = Path(__file__).resolve().parent


def make_fake_bin(root: Path) -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir()

    pixi = bin_dir / "pixi"
    pixi.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == \"--version\" ]]; then\n"
        "  echo 'pixi 0.42.1'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == \"run\" && \"${2:-}\" == \"Rscript\" && \"${3:-}\" == \"--version\" ]]; then\n"
        "  echo 'R scripting front-end version 4.4.1'\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unsupported fake pixi invocation: $*\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    pixi.chmod(0o755)

    nextflow = bin_dir / "nextflow"
    nextflow.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == \"-version\" ]]; then\n"
        "  echo 'nextflow version 24.10.0'\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unsupported fake nextflow invocation: $*\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    nextflow.chmod(0o755)
    return bin_dir


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="software-versions-spec-test-") as tmp:
        tmpdir = Path(tmp)
        spec_path = tmpdir / "software_versions_spec.yaml"
        spec_path.write_text(
            "tools:\n"
            "  - pixi\n"
            "  - nextflow\n"
            "  - R\n"
            "params:\n"
            "  - name: genome\n"
            "    env: EFFECTIVE_GENOME\n"
            "static:\n"
            "  - name: workflow\n"
            "    version_env: WORKFLOW_VERSION\n"
            "    repository_env: WORKFLOW_REPOSITORY\n",
            encoding="utf-8",
        )
        output_path = tmpdir / "software_versions.json"
        fake_bin = make_fake_bin(tmpdir)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["EFFECTIVE_GENOME"] = "GRCh38_with_ERCC"
        env["WORKFLOW_VERSION"] = "1.2.3"
        env["WORKFLOW_REPOSITORY"] = "https://example.test/workflow"

        completed = subprocess.run(
            [
                sys.executable,
                str(FUNCTIONS_DIR / "software_versions.py"),
                "--spec",
                str(spec_path),
                "--output",
                str(output_path),
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        versions = {entry["name"]: entry for entry in payload["software"]}
        assert versions["pixi"]["version"] == "pixi 0.42.1"
        assert versions["nextflow"]["version"] == "nextflow version 24.10.0"
        assert versions["R"]["version"] == "R scripting front-end version 4.4.1"
        assert versions["genome"]["version"] == "GRCh38_with_ERCC"
        assert versions["genome"]["source"] == "param"
        assert versions["workflow"]["version"] == "1.2.3"
        assert versions["workflow"]["repository"] == "https://example.test/workflow"
        assert versions["workflow"]["source"] == "static"

    print("software_versions function test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
