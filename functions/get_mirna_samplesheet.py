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
    entry = common.latest_entry(ctx)
    value = common.latest_output(ctx, "rendered_samplesheet")
    resolved = common.resolve_existing(value, ctx, entry)
    if resolved:
        return resolved
    value = common.latest_param(ctx, "samplesheet")
    resolved = common.resolve_existing(value, ctx, entry)
    if resolved:
        return resolved
    raise RuntimeError("samplesheet could not be resolved from the latest nfcore_smrnaseq run")
