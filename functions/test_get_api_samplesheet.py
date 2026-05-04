#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("get_api_samplesheet.py")
SPEC = importlib.util.spec_from_file_location("get_api_samplesheet", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

EXPECTED_FLOWCELL_API_BASE = "https://genomics.rwth-aachen.de/api/get/samples/flowcell/"


def make_ctx(template_root: Path, **resolved_params: object) -> SimpleNamespace:
    return SimpleNamespace(
        resolved_params=resolved_params,
        template=SimpleNamespace(root=template_root),
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="api-samplesheet-test-") as tmp:
        tmpdir = Path(tmp)
        fallback = tmpdir / "samplesheet.csv"
        fallback.write_text("fallback\n", encoding="utf-8")

        original_fetch = MODULE._fetch
        original_build_auth_header = MODULE._build_auth_header

        try:
            ctx = make_ctx(tmpdir, samplesheet="/tmp/explicit.csv", use_api_samplesheet=True)
            assert MODULE.resolve(ctx) == "/tmp/explicit.csv"

            ctx = make_ctx(tmpdir, samplesheet="", use_api_samplesheet=False)
            assert MODULE.resolve(ctx) == str(fallback.resolve())
            assert MODULE.API_BASE_FLOWCELL == EXPECTED_FLOWCELL_API_BASE

            ctx = make_ctx(
                tmpdir,
                bcl_dir="/data/run/260407_NB501289_0992_AHLHGVBGYX",
                flowcell_id="HLHGVBGYX",
                use_api_samplesheet=True,
            )
            MODULE._build_auth_header = lambda: "Basic token"
            calls: list[str] = []

            def fetch_flowcell_only(url: str, auth_header: str) -> bytes:
                calls.append(url)
                return b"api-flowcell\n"

            MODULE._fetch = fetch_flowcell_only
            resolved = Path(MODULE.resolve(ctx))
            assert resolved.read_text(encoding="utf-8") == "api-flowcell\n"
            assert calls == [f"{EXPECTED_FLOWCELL_API_BASE}HLHGVBGYX"]

            ctx = make_ctx(
                tmpdir,
                bcl_dir="/data/run/260407_NB501289_0992_AHLHGVBGYX",
                agendo_id="5616",
                use_api_samplesheet=True,
            )
            MODULE._build_auth_header = lambda: "Basic token"
            calls = []

            def fetch_with_flowcell_404(url: str, auth_header: str) -> bytes:
                calls.append(url)
                if "flowcell" in url:
                    raise MODULE.HTTPError(url, 404, "not found", hdrs=None, fp=None)
                return b"api-request\n"

            MODULE._fetch = fetch_with_flowcell_404
            resolved = Path(MODULE.resolve(ctx))
            assert resolved.read_text(encoding="utf-8") == "api-request\n"
            assert len(calls) == 2
            assert calls[0] == f"{EXPECTED_FLOWCELL_API_BASE}HLHGVBGYX"
            assert "request/5616" in calls[1]

            ctx = make_ctx(
                tmpdir,
                bcl_dir="/data/run/does_not_parse_",
                agendo_id="5616",
                use_api_samplesheet=True,
            )
            calls = []

            def fetch_request_only(url: str, auth_header: str) -> bytes:
                calls.append(url)
                return b"request-only\n"

            MODULE._fetch = fetch_request_only
            resolved = Path(MODULE.resolve(ctx))
            assert resolved.read_text(encoding="utf-8") == "request-only\n"
            assert calls == [f"{MODULE.API_BASE_REQUEST}5616"]

            ctx = make_ctx(
                tmpdir,
                bcl_dir="/data/run/260407_NB501289_0992_AHLHGVBGYX",
                agendo_id="5616",
                use_api_samplesheet=True,
            )
            MODULE._build_auth_header = lambda: (_ for _ in ()).throw(RuntimeError("missing creds"))
            assert MODULE.resolve(ctx) == str(fallback.resolve())
        finally:
            MODULE._fetch = original_fetch
            MODULE._build_auth_header = original_build_auth_header

    print("get_api_samplesheet tests passed")


if __name__ == "__main__":
    main()
