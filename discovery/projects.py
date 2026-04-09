from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .common import ensure_roots, list_child_directories, path_matches_query, summarize_directory

DEFAULT_PROJECT_ROOTS = [Path("/data/projects")]


def _project_data(path: Path) -> dict[str, Any]:
    project_file = path / "project.yaml"
    if not project_file.exists():
        return {}
    raw = yaml.safe_load(project_file.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def get_project_summary(path: str | Path) -> dict[str, Any]:
    project_path = Path(path).expanduser().resolve()
    data = _project_data(project_path)
    templates = data.get("templates") if isinstance(data.get("templates"), list) else []
    recent_templates = [
        str(entry.get("id") or entry.get("source_template") or "")
        for entry in templates[-5:]
        if isinstance(entry, dict) and (entry.get("id") or entry.get("source_template"))
    ]
    return summarize_directory(
        project_path,
        kind="project_summary",
        extra={
            "id": data.get("id") or project_path.name,
            "has_project_yaml": (project_path / "project.yaml").exists(),
            "active_pack": data.get("active_pack"),
            "packs": data.get("packs") if isinstance(data.get("packs"), list) else [],
            "linkar_runs": len(templates),
            "recent_templates": recent_templates,
        },
    )


def list_projects(roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    project_roots = ensure_roots(roots or DEFAULT_PROJECT_ROOTS)
    projects: list[dict[str, Any]] = []
    for root in project_roots:
        for path in list_child_directories(root):
            if not (path / "project.yaml").exists():
                continue
            projects.append(get_project_summary(path))
    return sorted(projects, key=lambda item: item["path"])


def find_projects(query: str, roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    return [item for item in list_projects(roots=roots) if path_matches_query(Path(item["path"]), query)]


def recent_projects(limit: int = 20, roots: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None) -> list[dict[str, Any]]:
    projects = list_projects(roots=roots)
    return sorted(projects, key=lambda item: item["mtime"], reverse=True)[:limit]
