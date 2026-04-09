from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import ensure_roots, path_matches_query, summarize_directory

DEFAULT_REFERENCE_ROOTS = [
    Path("/data/shared/10xGenomics/refs"),
    Path("/data/shared/references"),
]


def _reference_summary(path: Path, *, root: Path) -> dict[str, Any]:
    return summarize_directory(
        path,
        kind="reference_summary",
        extra={
            "root": str(root.resolve()),
        },
    )


def list_references(roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    reference_roots = ensure_roots(roots or DEFAULT_REFERENCE_ROOTS)
    references: list[dict[str, Any]] = []
    for root in reference_roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
            references.append(_reference_summary(path, root=root))
    return sorted(references, key=lambda item: item["path"])


def find_references(query: str, roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    return [item for item in list_references(roots=roots) if path_matches_query(Path(item["path"]), query)]


def recommended_references(
    *,
    organism: str | None = None,
    workflow: str | None = None,
    roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None,
) -> list[dict[str, Any]]:
    references = list_references(roots=roots)
    filters = [item.casefold() for item in (organism, workflow) if item]
    if not filters:
        return references
    ranked: list[tuple[int, dict[str, Any]]] = []
    for reference in references:
        haystack = f"{reference['name']} {reference['path']}".casefold()
        score = sum(1 for token in filters if token in haystack)
        if score:
            ranked.append((score, reference))
    return [item for _, item in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["name"]))]
