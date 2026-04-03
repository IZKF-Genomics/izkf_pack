from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_common():
    helper_path = Path(__file__).with_name("_dgea_common.py")
    spec = importlib.util.spec_from_file_location("izkf_pack_dgea_common", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load DGEA helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(ctx) -> str:
    common = _load_common()
    for key in ("samplesheet", "nfcore_samplesheet"):
        value = common.latest_param(ctx, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise RuntimeError(
        "samplesheet could not be resolved because no upstream nfcore samplesheet param was found in the current project"
    )
