from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.error import HTTPError, URLError


def _nonempty(value: object | None) -> str:
    return str(value or "").strip()


def _truthy(value: object | None, *, default: bool = True) -> bool:
    text = _nonempty(value)
    if not text:
        return default
    return text.lower() in {"1", "true", "yes", "on"}


def _load_api_module():
    path = Path(__file__).resolve().parent / "get_api_samplesheet.py"
    spec = importlib.util.spec_from_file_location("_izkf_get_api_samplesheet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load API samplesheet resolver: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _looks_like_aviti(resolved: dict[str, object], raw_run_dir: Path) -> bool:
    platform = _nonempty(resolved.get("platform")).lower()
    demultiplexer = _nonempty(resolved.get("demultiplexer")).lower()
    if platform == "aviti" or demultiplexer == "bases2fastq":
        return True
    if platform == "illumina" or demultiplexer == "bclconvert":
        return False
    return (raw_run_dir / "RunManifest.csv").exists()


def _cache_samplesheet(api_module: object, *, cache_key: str, content: bytes) -> str:
    out_dir = api_module._cache_root() / cache_key
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "samplesheet.csv"
    out_csv.write_bytes(content)
    return str(out_csv.resolve())


def _fetch_illumina_samplesheet(resolved: dict[str, object], raw_run_dir_value: str) -> str:
    api_module = _load_api_module()
    try:
        auth_header = api_module._build_auth_header()
    except RuntimeError as exc:
        raise RuntimeError("Missing GF_API_NAME/GF_API_PASS for Illumina GF API samplesheet lookup") from exc

    flowcell_id = _nonempty(resolved.get("flowcell_id")) or (api_module._parse_flowcell_id(raw_run_dir_value) or "")
    agendo_id = _nonempty(resolved.get("agendo_id"))
    if not flowcell_id and not agendo_id:
        raise RuntimeError(
            "Could not derive a flowcell id from raw_run_dir and no agendo_id was provided for samplesheet lookup"
        )

    errors: list[str] = []
    if flowcell_id:
        url = f"{api_module.API_BASE_FLOWCELL}{flowcell_id}"
        try:
            content = api_module._fetch(url, auth_header)
            return _cache_samplesheet(api_module, cache_key=flowcell_id, content=content)
        except HTTPError as exc:
            detail = api_module._extract_not_found_detail(exc) or exc.reason
            errors.append(f"flowcell {flowcell_id}: HTTP {exc.code} {detail}")
        except URLError as exc:
            errors.append(f"flowcell {flowcell_id}: {exc.reason}")

    if agendo_id:
        url = f"{api_module.API_BASE_REQUEST}{agendo_id}"
        try:
            content = api_module._fetch(url, auth_header)
            return _cache_samplesheet(api_module, cache_key=f"request_{agendo_id}", content=content)
        except HTTPError as exc:
            detail = api_module._extract_not_found_detail(exc) or exc.reason
            errors.append(f"request {agendo_id}: HTTP {exc.code} {detail}")
        except URLError as exc:
            errors.append(f"request {agendo_id}: {exc.reason}")

    joined = "; ".join(errors) if errors else "no API lookup was attempted"
    raise RuntimeError(f"No Illumina flowcell samplesheet found via GF API ({joined})")


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

    fallback = raw_run_dir / "SampleSheet.csv"
    use_api = _truthy(resolved.get("use_api_samplesheet"), default=True)
    api_error = ""
    if raw_run_dir_value and use_api:
        try:
            return _fetch_illumina_samplesheet(resolved, raw_run_dir_value)
        except RuntimeError as exc:
            api_error = str(exc)

    if raw_run_dir_value and fallback.exists():
        return str(fallback.resolve())

    if api_error:
        raise RuntimeError(api_error)

    raise RuntimeError(
        "flowcell_samplesheet could not be resolved. Pass --flowcell-samplesheet, enable "
        "--use-api-samplesheet, or place SampleSheet.csv in raw_run_dir."
    )
