#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_DIR = PACK_ROOT / "functions"
TEMPLATE_DIR = PACK_ROOT / "templates" / "dgea"


def main() -> int:
    source_settings = (TEMPLATE_DIR / ".vscode" / "settings.json").read_text(encoding="utf-8")
    assert "${workspaceFolder}/.pixi/envs/default/bin/R" in source_settings
    assert "${workspaceFolder}/.pixi/envs/default/bin/quarto" in source_settings

    with tempfile.TemporaryDirectory(prefix="dgea-vscode-settings-") as tmp:
        workspace_dir = Path(tmp) / "rendered_dgea"
        workspace_dir.mkdir(parents=True)

        completed = subprocess.run(
            [
                sys.executable,
                str(FUNCTIONS_DIR / "materialize_vscode_settings.py"),
                "--template-dir",
                str(TEMPLATE_DIR),
                "--workspace-dir",
                str(workspace_dir),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

        payload = json.loads((workspace_dir / ".vscode" / "settings.json").read_text(encoding="utf-8"))
        expected_r = f"{workspace_dir.resolve()}/.pixi/envs/default/bin/R"
        expected_quarto = f"{workspace_dir.resolve()}/.pixi/envs/default/bin/quarto"

        assert payload["positron.r.interpreters.default"] == expected_r
        assert payload["positron.r.customBinaries"] == [expected_r]
        assert payload["quarto.path"] == expected_quarto

    print("materialize_vscode_settings function test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
