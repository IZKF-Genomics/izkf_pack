from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_common():
    helper_path = Path(__file__).with_name("_scrnaseq_common.py")
    spec = importlib.util.spec_from_file_location("izkf_pack_scrnaseq_common", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load scRNA-seq helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(ctx) -> str:
    common = _load_common()
    name = common.selected_matrix_name(ctx).lower()
    if "cellbender" in name:
        return "cellbender"
    if "emptydrops" in name:
        return "emptydrops"
    return "none"
