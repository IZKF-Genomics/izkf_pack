from __future__ import annotations

from pathlib import Path
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


def project_root(ctx) -> Path | None:
    project = getattr(ctx, "project", None)
    if project is None:
        return None
    for attr in ("root", "path", "project_dir"):
        value = getattr(project, attr, None)
        if value:
            return Path(value).expanduser().resolve()
    data = getattr(project, "data", {}) or {}
    for key in ("root", "path", "project_dir"):
        value = data.get(key)
        if value:
            return Path(value).expanduser().resolve()
    return None


def latest_visible_output(
    ctx,
    relative_path: str,
    template_ids: tuple[str, ...] = UPSTREAM_TEMPLATE_IDS,
) -> str:
    root = project_root(ctx)
    if root is None:
        return ""
    entry = latest_entry(ctx, template_ids)
    if entry is None:
        return ""
    workspace = str(entry.get("path") or entry.get("history_path") or "").strip()
    if not workspace:
        return ""
    workspace_path = Path(workspace).expanduser()
    if not workspace_path.is_absolute():
        workspace_path = root / workspace_path
    candidate = (workspace_path / relative_path).resolve()
    return str(candidate) if candidate.exists() else ""


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
        "grcg7b": "ggallus",
        "hsapiens": "hsapiens",
        "mmusculus": "mmusculus",
        "rnorvegicus": "rnorvegicus",
        "sscrofa": "sscrofa",
        "drerio": "drerio",
        "ggallus": "ggallus",
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
