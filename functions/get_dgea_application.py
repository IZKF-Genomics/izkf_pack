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
    entry = common.latest_entry(ctx)
    if entry is None:
        return ""
    template_id = str(entry.get("id") or entry.get("source_template") or "")
    if template_id:
        return template_id
    return ""
