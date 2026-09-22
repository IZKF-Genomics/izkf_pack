from __future__ import annotations

import importlib.util
from pathlib import Path


def _common():
    path = Path(__file__).with_name("_mirna_differential_common.py")
    spec = importlib.util.spec_from_file_location("izkf_pack_mirna_common", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load miRNA helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(ctx) -> str:
    common = _common()
    edger_dir = common.latest_output(ctx, "edger_qc_dir")
    if isinstance(edger_dir, str) and edger_dir.strip():
        candidate = Path(edger_dir).expanduser() / "mature_counts.csv"
        if candidate.exists():
            return str(candidate.resolve())
    entry = common.latest_entry(ctx)
    workspace = common.entry_path(ctx, entry) if entry else None
    if workspace is not None:
        candidate = workspace / "results" / "mirna_quant" / "edger_qc" / "mature_counts.csv"
        if candidate.exists():
            return str(candidate.resolve())
    raise RuntimeError("mature_counts.csv could not be resolved from the latest nfcore_smrnaseq run")
