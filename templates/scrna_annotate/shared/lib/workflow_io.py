from __future__ import annotations

from pathlib import Path
import os

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW_CONFIG = ROOT / "config" / "workflow.yaml"


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"YAML config must be a mapping: {path}")
    return payload


def workflow_config_path() -> Path:
    raw = os.environ.get("SCRNA_ANNOTATE_WORKFLOW_CONFIG", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_WORKFLOW_CONFIG.resolve()


def load_workflow_config() -> tuple[dict, Path]:
    path = workflow_config_path()
    return read_yaml(path), path


def resolve_global_value(workflow_cfg: dict, key: str, default: str = "") -> str:
    global_cfg = workflow_cfg.get("global") if isinstance(workflow_cfg.get("global"), dict) else {}
    value = global_cfg.get(key, default)
    return str(value).strip() if value is not None else str(default).strip()


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
