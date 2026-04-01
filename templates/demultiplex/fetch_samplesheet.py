#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_FLOWCELL = os.environ.get(
    "GF_API_BASE_FLOWCELL",
    "https://genomics.rwth-aachen.de/api/get/samplesheet/flowcell/",
)
API_BASE_REQUEST = os.environ.get(
    "GF_API_BASE_REQUEST",
    "https://genomics.rwth-aachen.de/api/get/samplesheet/request/",
)


def parse_flowcell_id(bcl_dir: str) -> str | None:
    base = os.path.basename(os.path.normpath(bcl_dir or ""))
    if not base:
        return None
    parts = base.split("_")
    last = parts[-1] if parts else ""
    if not last:
        return None
    return last[1:] if len(last) >= 2 and last[0].isalpha() else last


def build_auth_header() -> str:
    user = (os.getenv("GF_API_NAME") or "").strip()
    password = (os.getenv("GF_API_PASS") or "").strip()
    if not user or not password:
        raise RuntimeError("Missing GF_API_NAME/GF_API_PASS for API samplesheet fetch")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def extract_not_found_detail(exc: HTTPError) -> str | None:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        detail = str(payload.get("detail") or "").strip()
        return detail or None
    return None


def fetch(url: str, auth_header: str) -> bytes:
    request = Request(url, headers={"Authorization": auth_header})
    with urlopen(request, timeout=20) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch samplesheet.csv from the facility API.")
    parser.add_argument("--bcl-dir", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--agendo-id", default="")
    parser.add_argument("--flowcell-id", default="")
    args = parser.parse_args()

    flowcell_id = (args.flowcell_id or "").strip() or parse_flowcell_id(args.bcl_dir)
    if not flowcell_id:
        raise RuntimeError("Could not determine flowcell_id from bcl_dir")

    auth_header = build_auth_header()
    target_url = f"{API_BASE_FLOWCELL}{flowcell_id}"
    source_label = f"flowcell {flowcell_id}"

    try:
        content = fetch(target_url, auth_header)
    except HTTPError as exc:
        if exc.code == 404 and args.agendo_id:
            target_url = f"{API_BASE_REQUEST}{args.agendo_id}"
            source_label = f"request {args.agendo_id}"
            try:
                content = fetch(target_url, auth_header)
            except HTTPError as nested:
                if nested.code == 404:
                    detail = extract_not_found_detail(nested)
                    if detail:
                        print(f"[fetch_samplesheet] {detail}")
                    return
                raise RuntimeError(f"HTTP {nested.code} from API for {source_label}") from nested
        elif exc.code == 404:
            detail = extract_not_found_detail(exc)
            if detail:
                print(f"[fetch_samplesheet] {detail}")
            return
        else:
            raise RuntimeError(f"HTTP {exc.code} from API for {source_label}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error fetching samplesheet: {exc}") from exc

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(content)
    print(f"[fetch_samplesheet] Downloaded samplesheet for {source_label} -> {args.out}")


if __name__ == "__main__":
    main()
