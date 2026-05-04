from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_FLOWCELL = os.environ.get(
    "GF_API_BASE_FLOWCELL",
    "https://genomics.rwth-aachen.de/api/get/samples/flowcell/",
)
API_BASE_REQUEST = os.environ.get(
    "GF_API_BASE_REQUEST",
    "https://genomics.rwth-aachen.de/api/get/samplesheet/request/",
)


def _nonempty(value: object | None) -> str:
    text = str(value or "").strip()
    return text


def _parse_flowcell_id(bcl_dir: str) -> str | None:
    base = os.path.basename(os.path.normpath(bcl_dir or ""))
    if not base:
        return None
    parts = base.split("_")
    last = parts[-1] if parts else ""
    if not last:
        return None
    return last[1:] if len(last) >= 2 and last[0].isalpha() else last


def _build_auth_header() -> str:
    user = _nonempty(os.getenv("GF_API_NAME"))
    password = _nonempty(os.getenv("GF_API_PASS"))
    if not user or not password:
        raise RuntimeError("Missing GF_API_NAME/GF_API_PASS for API samplesheet lookup")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _extract_not_found_detail(exc: HTTPError) -> str | None:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        detail = _nonempty(payload.get("detail"))
        return detail or None
    return None


def _fetch(url: str, auth_header: str) -> bytes:
    request = Request(url, headers={"Authorization": auth_header})
    with urlopen(request, timeout=20) as response:
        return response.read()


def _cache_root() -> Path:
    linkar_home = _nonempty(os.getenv("LINKAR_HOME"))
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "api_samplesheets"
    return Path.home().resolve() / ".linkar" / "api_samplesheets"


def _fallback_template_samplesheet(ctx) -> str:
    fallback = Path(ctx.template.root) / "samplesheet.csv"
    if fallback.exists():
        return str(fallback.resolve())
    raise RuntimeError(
        "No samplesheet found in the API and the template does not provide a fallback samplesheet.csv"
    )


def resolve(ctx) -> str:
    resolved = ctx.resolved_params or {}

    explicit_samplesheet = _nonempty(resolved.get("samplesheet"))
    if explicit_samplesheet:
        return explicit_samplesheet

    use_api = bool(resolved.get("use_api_samplesheet", True))
    if not use_api:
        return _fallback_template_samplesheet(ctx)

    bcl_dir = _nonempty(resolved.get("bcl_dir"))
    if not bcl_dir:
        return _fallback_template_samplesheet(ctx)

    agendo_id = _nonempty(resolved.get("agendo_id"))
    flowcell_id = _nonempty(resolved.get("flowcell_id")) or (_parse_flowcell_id(bcl_dir) or "")
    if not flowcell_id and not agendo_id:
        return _fallback_template_samplesheet(ctx)

    try:
        auth_header = _build_auth_header()
    except RuntimeError:
        return _fallback_template_samplesheet(ctx)

    content: bytes | None = None
    cache_key = ""
    source_label = ""

    if flowcell_id:
        cache_key = flowcell_id
        source_label = f"flowcell {flowcell_id}"
        target_url = f"{API_BASE_FLOWCELL}{flowcell_id}"
        try:
            content = _fetch(target_url, auth_header)
        except HTTPError as exc:
            if exc.code != 404:
                return _fallback_template_samplesheet(ctx)
        except URLError:
            return _fallback_template_samplesheet(ctx)

    if content is None and agendo_id:
        cache_key = f"request_{agendo_id}"
        source_label = f"request {agendo_id}"
        target_url = f"{API_BASE_REQUEST}{agendo_id}"
        try:
            content = _fetch(target_url, auth_header)
        except HTTPError as nested:
            if nested.code == 404:
                return _fallback_template_samplesheet(ctx)
            return _fallback_template_samplesheet(ctx)
        except URLError:
            return _fallback_template_samplesheet(ctx)

    if content is None:
        return _fallback_template_samplesheet(ctx)

    out_dir = _cache_root() / cache_key
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "samplesheet.csv"
    out_csv.write_bytes(content)
    return str(out_csv)
