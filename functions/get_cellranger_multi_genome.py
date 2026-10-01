from __future__ import annotations


def resolve(ctx) -> str:
    project = getattr(ctx, "project", None)
    entries = ((getattr(project, "data", {}) or {}).get("templates") or []) if project is not None else []
    for entry in reversed(entries):
        if not isinstance(entry, dict):
            continue
        genome = str((entry.get("params") or {}).get("genome") or "").strip()
        if genome and not genome.startswith("__EDIT_ME_"):
            return genome
    warn = getattr(ctx, "warn", None)
    if callable(warn):
        warn(
            "Genome could not be inferred from existing project metadata.",
            action="Edit config/cellranger_multi.toml after rendering.",
            fallback="",
        )
    return ""
