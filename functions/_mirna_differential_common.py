from __future__ import annotations

from pathlib import Path
from typing import Any


UPSTREAM_TEMPLATE_IDS = ("nfcore_smrnaseq",)


def templates(ctx) -> list[dict[str, Any]]:
    if ctx.project is None:
        return []
    data = getattr(ctx.project, "data", {}) or {}
    return [item for item in (data.get("templates") or []) if isinstance(item, dict)]


def latest_entry(ctx) -> dict[str, Any] | None:
    for entry in reversed(templates(ctx)):
        template_id = str(entry.get("id") or entry.get("source_template") or "")
        if template_id in UPSTREAM_TEMPLATE_IDS:
            return entry
    return None


def latest_output(ctx, key: str) -> Any:
    value = ctx.latest_output(key, template_id="nfcore_smrnaseq")
    if value:
        return value
    entry = latest_entry(ctx)
    outputs = (entry or {}).get("outputs") or {}
    return outputs.get(key) if isinstance(outputs, dict) else None


def latest_param(ctx, key: str) -> Any:
    entry = latest_entry(ctx)
    params = (entry or {}).get("params") or {}
    return params.get(key) if isinstance(params, dict) else None


def project_root(ctx) -> Path | None:
    root = getattr(getattr(ctx, "project", None), "root", None)
    return Path(root).resolve() if root else None


def entry_path(ctx, entry: dict[str, Any]) -> Path | None:
    value = entry.get("path") or entry.get("history_path")
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    root = project_root(ctx)
    return ((root / path) if root else path).resolve()


def resolve_existing(value: object, ctx, entry: dict[str, Any] | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    path = Path(value.strip()).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    workspace = entry_path(ctx, entry) if entry is not None else None
    if workspace is not None:
        return str((workspace / path).resolve())
    root = project_root(ctx)
    return str(((root / path) if root else path).resolve())


def map_genome_to_organism(value: object) -> str:
    genome = str(value or "").strip().lower()
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
        "grcg7b": "ggallus",
        "hsapiens": "hsapiens",
        "mmusculus": "mmusculus",
        "rnorvegicus": "rnorvegicus",
        "sscrofa": "sscrofa",
        "ggallus": "ggallus",
    }
    return mapping.get(genome, "")
