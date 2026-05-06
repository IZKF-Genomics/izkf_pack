from __future__ import annotations

import importlib.util
from pathlib import Path


GENOME_PLACEHOLDER = "__EDIT_ME_GENOME__"
OTHER_ORGANISM_FIELD = 'specify "other" organism'


def _load_agendo_common():
    helper_path = Path(__file__).with_name("_agendo_common.py")
    spec = importlib.util.spec_from_file_location("izkf_pack_agendo_common", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Agendo helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _field_value(metadata: dict[str, object], field_name: str) -> str:
    fields = metadata.get("fields")
    if not isinstance(fields, list):
        return ""
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").replace("&quot;", '"').strip().lower()
        if name == field_name:
            return str(field.get("value") or "").strip()
    return ""


def _organism_from_metadata(metadata: dict[str, object], common) -> str:
    organism = common.nonempty(metadata.get("organism"))
    if organism.lower() == "other":
        specified = _field_value(metadata, OTHER_ORGANISM_FIELD)
        if specified:
            return specified
    return organism


def resolve(ctx) -> str:
    common = _load_agendo_common()
    if not common.nonempty((ctx.resolved_params or {}).get("agendo_id")):
        ctx.warn(
            "No agendo_id provided; could not derive genome from Agendo metadata.",
            action="Pass --agendo-id or rerender with --genome before execution.",
            fallback=GENOME_PLACEHOLDER,
        )
        return GENOME_PLACEHOLDER
    metadata = common.resolve_request_metadata(ctx)
    organism = _organism_from_metadata(metadata, common).lower()
    mapping = {
        "human": "GRCh38",
        "mouse": "GRCm39",
        "rat": "mRatBN7.2",
        "pig": "Sscrofa11.1",
        "zebrafish": "GRCz11",
        "danio rerio": "GRCz11",
        "chicken": "GRCg7b",
        "gallus gallus": "GRCg7b",
        "gallus gallus domesticus": "GRCg7b",
    }
    genome = mapping.get(organism)
    if not genome:
        ctx.warn(
            f"Could not derive genome from Agendo organism '{organism}'.",
            action="Rerender with --genome or edit the generated parameters before execution.",
            fallback=GENOME_PLACEHOLDER,
        )
        return GENOME_PLACEHOLDER
    return genome
