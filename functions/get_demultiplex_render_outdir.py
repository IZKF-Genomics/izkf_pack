from __future__ import annotations

import os
from pathlib import Path


def resolve(ctx) -> str:
    resolved = ctx.resolved_params or {}
    input_dir = Path(str(resolved.get("input_dir") or resolved.get("bcl_dir") or "")).expanduser()
    run_name = input_dir.name.strip()
    if not run_name:
        raise RuntimeError("input_dir or bcl_dir must resolve before demultiplex outdir can be derived")

    target_root = Path(os.environ.get("IZKF_DEMULTIPLEX_RENDER_ROOT", "/data/fastq")).expanduser()
    return str((target_root / run_name).resolve())
