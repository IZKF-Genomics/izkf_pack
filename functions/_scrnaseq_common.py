from __future__ import annotations

from typing import Any


UPSTREAM_TEMPLATE_IDS = ("nfcore_scrnaseq",)


def _templates(ctx) -> list[dict[str, Any]]:
    if ctx.project is None:
        return []
    data = getattr(ctx.project, "data", {}) or {}
    templates = data.get("templates") or []
    return [entry for entry in templates if isinstance(entry, dict)]


def latest_entry(ctx, template_ids: tuple[str, ...] = UPSTREAM_TEMPLATE_IDS) -> dict[str, Any] | None:
    templates = _templates(ctx)
    for entry in reversed(templates):
        template_id = str(entry.get("id") or entry.get("source_template") or "")
        if template_id in template_ids:
            return entry
    return None


def latest_output(ctx, key: str, template_ids: tuple[str, ...] = UPSTREAM_TEMPLATE_IDS) -> Any:
    for template_id in template_ids:
        value = ctx.latest_output(key, template_id=template_id)
        if value:
            return value
    entry = latest_entry(ctx, template_ids)
    if entry is None:
        return None
    outputs = entry.get("outputs") or {}
    if isinstance(outputs, dict):
        return outputs.get(key)
    return None


def latest_param(ctx, key: str, template_ids: tuple[str, ...] = UPSTREAM_TEMPLATE_IDS) -> Any:
    entry = latest_entry(ctx, template_ids)
    if entry is None:
        return None
    params = entry.get("params") or {}
    if isinstance(params, dict):
        return params.get(key)
    return None


def map_genome_to_organism(genome: object) -> str:
    value = str(genome or "").strip().lower()
    mapping = {
        "grch38": "hsapiens",
        "hg38": "hsapiens",
        "grcm39": "mmusculus",
        "grcm38": "mmusculus",
        "mm10": "mmusculus",
        "mratbn7.2": "rnorvegicus",
        "rn7": "rnorvegicus",
        "sscrofa11.1": "sscrofa",
        "susscr11": "sscrofa",
        "grcz11": "drerio",
        "danrer11": "drerio",
        "hsapiens": "hsapiens",
        "mmusculus": "mmusculus",
        "rnorvegicus": "rnorvegicus",
        "sscrofa": "sscrofa",
        "drerio": "drerio",
    }
    return mapping.get(value, "")


def selected_matrix_name(ctx) -> str:
    value = latest_output(ctx, "selected_matrix_h5ad")
    if not isinstance(value, str):
        return ""
    path = value.strip()
    if not path:
        return ""
    return path.rsplit("/", 1)[-1]
