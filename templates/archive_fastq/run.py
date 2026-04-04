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
    template_id="archive_fastq",
    source_root="/data/fastq",
    target_root="/mnt/nextgen2/archive/fastq",
    manifest_prefix="archive_fastq",
    layout="flat",
    cleanup_allowed=True,
    exclude_patterns=(
        "*.fastq.gz",
        "*.fq.gz",
        ".pixi",
        "work",
        ".renv",
        ".Rproj.user",
        ".nextflow",
        ".nextflow.log*",
        "nohup.out",
        "Logs",
        "Reports",
    ),
)


if __name__ == "__main__":
    raise SystemExit(execute(PROFILE))
