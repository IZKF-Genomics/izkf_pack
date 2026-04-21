from __future__ import annotations

import importlib.util
from pathlib import Path


UPSTREAM_TEMPLATE_IDS = ("scverse_scrna_prep",)
EXPECTED_BASENAME = "adata.prep.h5ad"


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
    value = common.latest_output(ctx, "scrna_prep_h5ad", template_ids=UPSTREAM_TEMPLATE_IDS)
    if isinstance(value, str) and value.strip():
        return value.strip()

    fallback = common.latest_output(ctx, "h5ad_outputs", template_ids=UPSTREAM_TEMPLATE_IDS)
    if isinstance(fallback, list):
        for item in fallback:
            if not isinstance(item, str):
                continue
            candidate = item.strip()
            if candidate.endswith("/" + EXPECTED_BASENAME) or candidate == EXPECTED_BASENAME:
                return candidate
    return ""
