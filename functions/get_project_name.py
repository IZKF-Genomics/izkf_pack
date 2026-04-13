from __future__ import annotations


def resolve(ctx) -> str:
    if ctx.project is None:
        return ""
    return str(getattr(ctx.project, "name", "") or "")
