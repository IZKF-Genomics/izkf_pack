#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


def make_fake_rsync(bin_dir: Path) -> None:
    script = """#!/usr/bin/env python3
from __future__ import annotations
import shutil
import sys
from pathlib import Path

args = sys.argv[1:]
exclude = []
clean = []
i = 0
while i < len(args):
    if args[i] == "--exclude":
        exclude.append(args[i + 1])
        i += 2
        continue
    clean.append(args[i])
    i += 1

if "-avhn" in clean:
    sys.exit(0)

src = Path(clean[-2])
dst_parent = Path(clean[-1])
dst_parent.mkdir(parents=True, exist_ok=True)
dst = dst_parent / src.name
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*exclude))
"""
    path = bin_dir / "rsync"
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        source_root = root / "projects"
        target_root = root / "archive"
        manifest_dir = root / "manifests"
        run_dir = source_root / "240101_PROJECT_TEST"
        run_dir.mkdir(parents=True)
        target_root.mkdir()
        (run_dir / "report.txt").write_text("ok\n", encoding="utf-8")
        (run_dir / "results").mkdir(parents=True, exist_ok=True)
        (run_dir / "results" / "old.txt").write_text("old\n", encoding="utf-8")
        results_dir = root / "results"
        fake_bin = root / "bin"
        fake_bin.mkdir()
        make_fake_rsync(fake_bin)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        completed = subprocess.run(
            [
                sys.executable,
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results_dir),
                "--source-root",
                str(source_root),
                "--target-root",
                str(target_root),
                "--manifest-dir",
                str(manifest_dir),
                "--min-free-gb",
                "0",
                "--yes",
                "true",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        assert "Completed runs: 1" in completed.stdout
        manifest_path = Path((results_dir / "manifest_path.txt").read_text(encoding="utf-8").strip())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["workflow"] == "archive_projects"
        assert manifest["records"][0]["status"] == "completed"
        assert not run_dir.exists()
        assert (target_root / "240101_PROJECT_TEST" / "report.txt").exists()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
