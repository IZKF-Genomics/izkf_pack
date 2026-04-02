from __future__ import annotations

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_REQUEST = os.environ.get(
    "GF_API_BASE_REQUEST_METADATA",
    "https://genomics.rwth-aachen.de/api/get/request/",
)


def _nonempty(value: object | None) -> str:
    return str(value or "").strip()


def _build_auth_header() -> str:
    user = _nonempty(os.getenv("GF_API_NAME"))
    password = _nonempty(os.getenv("GF_API_PASS"))
    if not user or not password:
        raise RuntimeError("Missing GF_API_NAME/GF_API_PASS for Agendo metadata lookup")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _fetch_request(agendo_id: str) -> dict[str, object]:
    request = Request(
        f"{API_BASE_REQUEST}{agendo_id}",
        headers={"Authorization": _build_auth_header(), "Accept": "application/json"},
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


def resolve(ctx) -> str:
    agendo_id = _nonempty((ctx.resolved_params or {}).get("agendo_id"))
    if not agendo_id:
        raise RuntimeError("agendo_id must be provided or genome must be set explicitly")

    organism = _nonempty(_fetch_request(agendo_id).get("organism")).lower()
    mapping = {
        "human": "GRCh38",
        "mouse": "GRCm39",
        "rat": "mRatBN7.2",
        "pig": "Sscrofa11.1",
    }
    genome = mapping.get(organism)
    if not genome:
        raise RuntimeError(f"Unsupported organism '{organism}' for genome derivation")
    return genome
