from __future__ import annotations

import os
from pathlib import Path


def resolve(ctx) -> str:
    resolved = ctx.resolved_params or {}
    bcl_dir = Path(str(resolved.get("bcl_dir") or "")).expanduser()
    run_name = bcl_dir.name.strip()
    if not run_name:
        raise RuntimeError("bcl_dir must resolve before demultiplex outdir can be derived")

    target_root = Path(os.environ.get("IZKF_DEMULTIPLEX_RENDER_ROOT", "/data/fastq")).expanduser()
    return str((target_root / run_name).resolve())
