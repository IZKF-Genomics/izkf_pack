from __future__ import annotations

import os
import re
from pathlib import Path


def _normalize_run_name(name: str) -> str:
    match = re.match(r"^(20\d{6})_(.+)$", name)
    if match:
        date, rest = match.groups()
        return f"{date[2:]}_{rest}"
    return name


def resolve(ctx) -> str:
    resolved = ctx.resolved_params or {}
    raw_run_dir = Path(str(resolved.get("raw_run_dir") or "")).expanduser()
    run_name = _normalize_run_name(raw_run_dir.name.strip())
    if not run_name:
        raise RuntimeError("raw_run_dir must resolve before nfcore_demultiplex outdir can be derived")

    target_root = Path(os.environ.get("IZKF_DEMULTIPLEX_RENDER_ROOT", "/data/fastq")).expanduser()
    return str((target_root / run_name).resolve())
