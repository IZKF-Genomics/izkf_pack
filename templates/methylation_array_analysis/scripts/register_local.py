#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from registry_common import load_registry, save_registry, upsert_dataset, workspace_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register a local IDAT dataset in config/datasets.toml.")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--array-type", default="EPIC_V2")
    parser.add_argument("--source", default="local")
    parser.add_argument("--enabled", default="true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    doc = load_registry()
    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"Local dataset path does not exist: {path}")

    try:
        stored_path = str(path.relative_to(workspace_root()))
    except ValueError:
        stored_path = str(path)

    upsert_dataset(
        doc,
        args.dataset_id,
        {
            "source": args.source,
            "path": stored_path,
            "array_type": args.array_type,
            "enabled": args.enabled.lower() != "false",
        },
    )
    save_registry(doc)
    print(f"[INFO] Registered dataset {args.dataset_id} -> {stored_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
