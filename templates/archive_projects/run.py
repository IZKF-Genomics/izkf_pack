#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "_archive_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from archive_engine import ArchiveProfile, execute


PROFILE = ArchiveProfile(
    template_id="archive_projects",
    source_root="/data/projects",
    target_root="/mnt/nextgen2/archive/projects",
    manifest_prefix="archive_projects",
    layout="flat",
    cleanup_allowed=True,
    exclude_patterns=("work", ".pixi", ".renv", ".nextflow", "results", "*.fastq.gz"),
)


if __name__ == "__main__":
    raise SystemExit(execute(PROFILE))
