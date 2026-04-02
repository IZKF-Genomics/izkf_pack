from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_REQUEST = os.environ.get(
    "GF_API_BASE_REQUEST_METADATA",
    "https://genomics.rwth-aachen.de/api/get/request/",
)


def nonempty(value: object | None) -> str:
    return str(value or "").strip()


def build_auth_header() -> str:
    user = nonempty(os.getenv("GF_API_NAME"))
    password = nonempty(os.getenv("GF_API_PASS"))
    if not user or not password:
        raise RuntimeError("Missing GF_API_NAME/GF_API_PASS for Agendo metadata lookup")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def cache_root() -> Path:
    linkar_home = nonempty(os.getenv("LINKAR_HOME"))
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "agendo"
    return Path.home().resolve() / ".linkar" / "agendo"


def get_agendo_id(ctx) -> str:
    agendo_id = nonempty((ctx.resolved_params or {}).get("agendo_id"))
    if not agendo_id:
        raise RuntimeError("agendo_id must be provided to resolve Agendo metadata")
    return agendo_id


def fetch_request_metadata(agendo_id: str) -> dict[str, object]:
    request = Request(
        f"{API_BASE_REQUEST}{agendo_id}",
        headers={"Authorization": build_auth_header(), "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while fetching Agendo request {agendo_id}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error while fetching Agendo request {agendo_id}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Agendo payload for request {agendo_id}")
    return payload


def load_cached_request_metadata(agendo_id: str) -> dict[str, object]:
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    cache_file = root / f"{agendo_id}.json"

    if cache_file.exists():
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return payload

    payload = fetch_request_metadata(agendo_id)
    cache_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def resolve_request_metadata(ctx) -> dict[str, object]:
    agendo_id = get_agendo_id(ctx)
    return load_cached_request_metadata(agendo_id)
