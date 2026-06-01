#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize template .vscode/settings.json with an absolute workspace path."
    )
    parser.add_argument("--template-dir", required=True, help="Template directory containing .vscode/settings.json.")
    parser.add_argument("--workspace-dir", required=True, help="Rendered workspace directory to write into.")
    return parser.parse_args()


def materialize_settings(*, template_dir: Path, workspace_dir: Path) -> Path:
    source_path = template_dir / ".vscode" / "settings.json"
    destination_path = workspace_dir / ".vscode" / "settings.json"

    settings = json.loads(source_path.read_text(encoding="utf-8"))
    workspace_root = str(workspace_dir.resolve())

    rendered = json.loads(json.dumps(settings).replace("${workspaceFolder}", workspace_root))
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text(json.dumps(rendered, indent=2) + "\n", encoding="utf-8")
    return destination_path


def main() -> int:
    args = parse_args()
    materialize_settings(
        template_dir=Path(args.template_dir).resolve(),
        workspace_dir=Path(args.workspace_dir).resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
