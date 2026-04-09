from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import ensure_roots, list_child_directories, path_matches_query, summarize_directory

DEFAULT_FASTQ_ROOTS = [Path("/data/fastq")]
FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz")


def _fastq_run_summary(path: Path) -> dict[str, Any]:
    fastq_files = sorted(
        item.name for item in path.iterdir() if item.is_file() and any(item.name.endswith(suffix) for suffix in FASTQ_SUFFIXES)
    ) if path.exists() else []
    return summarize_directory(
        path,
        kind="fastq_run_summary",
        extra={
            "fastq_file_count": len(fastq_files),
            "example_fastq_files": fastq_files[:5],
        },
    )


def list_fastq_runs(roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    fastq_roots = ensure_roots(roots or DEFAULT_FASTQ_ROOTS)
    runs: list[dict[str, Any]] = []
    for root in fastq_roots:
        for path in list_child_directories(root):
            runs.append(_fastq_run_summary(path))
    return sorted(runs, key=lambda item: item["path"])


def find_fastq_runs(query: str, roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    return [item for item in list_fastq_runs(roots=roots) if path_matches_query(Path(item["path"]), query)]


def recent_fastq_runs(limit: int = 20, roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    runs = list_fastq_runs(roots=roots)
    return sorted(runs, key=lambda item: item["mtime"], reverse=True)[:limit]
