from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import ensure_roots, list_child_directories, path_matches_query, summarize_directory

DEFAULT_RAW_ROOTS = [Path("/data/raw")]
SAMPLE_SHEET_NAMES = ("SampleSheet.csv", "sample_sheet.csv", "samplesheet.csv")
RUN_NAME_PATTERN = re.compile(r"^\d{6}[_-]")


def _instrument_name(path: Path, configured_root: Path) -> str | None:
    try:
        relative = path.relative_to(configured_root)
    except ValueError:
        return configured_root.name
    return relative.parts[0] if len(relative.parts) > 1 else configured_root.name


def _raw_run_summary(path: Path, *, instrument: str | None) -> dict[str, Any]:
    has_samplesheet = any((path / candidate).exists() for candidate in SAMPLE_SHEET_NAMES)
    return summarize_directory(
        path,
        kind="raw_run_summary",
        extra={
            "instrument": instrument,
            "has_samplesheet": has_samplesheet,
        },
    )


def list_raw_runs(roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    raw_roots = ensure_roots(roots or DEFAULT_RAW_ROOTS)
    runs: list[dict[str, Any]] = []
    for root in raw_roots:
        children = list_child_directories(root)
        if not children:
            continue
        first_level_has_runs = any(RUN_NAME_PATTERN.match(child.name) for child in children)
        if first_level_has_runs:
            for path in children:
                runs.append(_raw_run_summary(path, instrument=root.name))
            continue
        for instrument_root in children:
            for path in list_child_directories(instrument_root):
                runs.append(_raw_run_summary(path, instrument=_instrument_name(path, root)))
    return sorted(runs, key=lambda item: item["path"])


def find_raw_runs(query: str, roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    return [item for item in list_raw_runs(roots=roots) if path_matches_query(Path(item["path"]), query)]


def recent_raw_runs(limit: int = 20, roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    runs = list_raw_runs(roots=roots)
    return sorted(runs, key=lambda item: item["mtime"], reverse=True)[:limit]
