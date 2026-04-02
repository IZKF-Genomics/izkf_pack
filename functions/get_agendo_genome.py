from __future__ import annotations

import importlib.util
from pathlib import Path


GENOME_PLACEHOLDER = "__EDIT_ME_GENOME__"


def _load_agendo_common():
    helper_path = Path(__file__).with_name("_agendo_common.py")
    spec = importlib.util.spec_from_file_location("izkf_pack_agendo_common", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Agendo helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(ctx) -> str:
    common = _load_agendo_common()
    organism = common.nonempty(common.resolve_request_metadata(ctx).get("organism")).lower()
    mapping = {
        "human": "GRCh38",
        "mouse": "GRCm39",
        "rat": "mRatBN7.2",
        "pig": "Sscrofa11.1",
    }
    genome = mapping.get(organism)
    if not genome:
        ctx.warn(
            f"Could not derive genome from Agendo organism '{organism}'.",
            action=f"Edit run.sh and replace {GENOME_PLACEHOLDER} before execution.",
            fallback=GENOME_PLACEHOLDER,
        )
        return GENOME_PLACEHOLDER
    return genome
