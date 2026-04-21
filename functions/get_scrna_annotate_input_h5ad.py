from __future__ import annotations

import importlib.util
from pathlib import Path


PREFERRED_TEMPLATE_OUTPUTS = (
    ("scrna_prep", "scrna_prep_h5ad"),
    ("scrna_integrate", "integrated_h5ad"),
)


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
    for template_id, output_key in PREFERRED_TEMPLATE_OUTPUTS:
        value = common.latest_output(ctx, output_key, template_ids=(template_id,))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
