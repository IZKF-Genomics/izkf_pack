#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_PATTERNS = (
    "discovery/test_*.py",
    "functions/test_*.py",
    "templates/*/test.py",
)


def discover_tests() -> list[Path]:
    return sorted({path for pattern in TEST_PATTERNS for path in ROOT.glob(pattern)})


def main() -> int:
    tests = discover_tests()
    if not tests:
        print("No tests found", file=sys.stderr)
        return 1

    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(ROOT), current_pythonpath) if value
    )

    for index, test_path in enumerate(tests, start=1):
        relative_path = test_path.relative_to(ROOT)
        print(f"[{index}/{len(tests)}] {relative_path}", flush=True)
        completed = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=ROOT,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            print(f"FAILED: {relative_path}", file=sys.stderr)
            return completed.returncode

    print(f"All {len(tests)} test scripts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
