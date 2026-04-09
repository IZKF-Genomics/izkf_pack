from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def ensure_roots(roots: str | Path | list[str | Path] | tuple[str | Path, ...] | None) -> list[Path]:
    if roots is None:
        return []
    if isinstance(roots, (str, Path)):
        values = [roots]
    else:
        values = list(roots)
    cleaned: list[Path] = []
    for value in values:
        path = Path(value).expanduser()
        if path in cleaned:
            continue
        cleaned.append(path)
    return cleaned


def isoformat_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def path_matches_query(path: Path, query: str | None) -> bool:
    if not query:
        return True
    needle = query.casefold()
    return needle in path.name.casefold() or needle in str(path).casefold()


def summarize_directory(path: Path, *, kind: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "kind": kind,
        "name": path.name,
        "path": str(path.resolve()),
        "mtime": isoformat_mtime(path),
    }
    if extra:
        payload.update(extra)
    return payload


def list_child_directories(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    return sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name)
