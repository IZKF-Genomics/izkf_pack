from __future__ import annotations

from typing import Any


UPSTREAM_TEMPLATE_IDS = ("nfcore_3mrnaseq", "nfcore_rnaseq")


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


def project_author_names(ctx) -> str:
    if ctx.project is None:
        return ""
    data = getattr(ctx.project, "data", {}) or {}
    author = data.get("author")
    if isinstance(author, dict):
        name = str(author.get("name") or "").strip()
        if name:
            return name
    authors = data.get("authors") or []
    names: list[str] = []
    if isinstance(authors, list):
        for item in authors:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    names.append(name)
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
    return ", ".join(names)


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
        "grcg7b": "ggallus",
        "hsapiens": "hsapiens",
        "mmusculus": "mmusculus",
        "rnorvegicus": "rnorvegicus",
        "sscrofa": "sscrofa",
        "drerio": "drerio",
        "ggallus": "ggallus",
    }
    return mapping.get(value, "")
