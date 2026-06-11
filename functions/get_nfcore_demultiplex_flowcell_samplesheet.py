from __future__ import annotations

import importlib.util
from pathlib import Path


def _nonempty(value: object | None) -> str:
    return str(value or "").strip()


def _load_get_api_samplesheet():
    path = Path(__file__).resolve().parent / "get_api_samplesheet.py"
    spec = importlib.util.spec_from_file_location("_izkf_get_api_samplesheet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load API samplesheet resolver: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve


class _CompatContext:
    def __init__(self, template: object, resolved_params: dict[str, object]) -> None:
        self.template = template
        self.resolved_params = resolved_params


def _looks_like_aviti(resolved: dict[str, object], raw_run_dir: Path) -> bool:
    platform = _nonempty(resolved.get("platform")).lower()
    demultiplexer = _nonempty(resolved.get("demultiplexer")).lower()
    if platform == "aviti" or demultiplexer == "bases2fastq":
        return True
    if platform == "illumina" or demultiplexer == "bclconvert":
        return False
    return (raw_run_dir / "RunManifest.csv").exists()


def resolve(ctx) -> str:
    resolved = dict(ctx.resolved_params or {})

    explicit = _nonempty(resolved.get("flowcell_samplesheet"))
    if explicit:
        return explicit

    raw_run_dir_value = _nonempty(resolved.get("raw_run_dir"))
    raw_run_dir = Path(raw_run_dir_value).expanduser() if raw_run_dir_value else Path()
    if raw_run_dir_value and _looks_like_aviti(resolved, raw_run_dir):
        manifest = raw_run_dir / "RunManifest.csv"
        if manifest.exists():
            return str(manifest.resolve())

    compat_params = dict(resolved)
    compat_params["samplesheet"] = ""
    compat_params["bcl_dir"] = raw_run_dir_value
    return _load_get_api_samplesheet()(_CompatContext(ctx.template, compat_params))
