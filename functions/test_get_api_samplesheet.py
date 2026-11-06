#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("get_api_samplesheet.py")
SPEC = importlib.util.spec_from_file_location("get_api_samplesheet", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

EXPECTED_FLOWCELL_API_BASE = "https://genomics.rwth-aachen.de/api/get/samplesheet/flowcell/"


class FakeContext:
    def __init__(self, template_root: Path, **resolved_params: object) -> None:
        self.resolved_params = resolved_params
        self.template = SimpleNamespace(root=template_root)
        self.warnings: list[dict[str, object]] = []

    def warn(self, message: str, **kwargs: object) -> None:
        self.warnings.append({"message": message, **kwargs})


def make_bundle(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def expect_runtime_error(call, text: str) -> None:
    try:
        call()
    except RuntimeError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected RuntimeError containing: {text}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="api-samplesheet-test-") as tmp:
        tmpdir = Path(tmp)
        fallback = tmpdir / "samplesheet.csv"
        fallback.write_text("fallback\n", encoding="utf-8")

        original_fetch = MODULE._fetch
        original_build_auth_header = MODULE._build_auth_header
        original_linkar_home = os.environ.get("LINKAR_HOME")
        original_max_download = MODULE.MAX_BUNDLE_DOWNLOAD_BYTES
        original_max_bytes = MODULE.MAX_BUNDLE_UNCOMPRESSED_BYTES
        os.environ["LINKAR_HOME"] = str(tmpdir / "linkar-home")

        try:
            ctx = FakeContext(tmpdir, samplesheet="/tmp/explicit.csv", use_api_samplesheet=True)
            assert MODULE.resolve(ctx) == "/tmp/explicit.csv"

            ctx = FakeContext(tmpdir, samplesheet="", use_api_samplesheet=False)
            assert MODULE.resolve(ctx) == str(fallback.resolve())
            assert MODULE.API_BASE_FLOWCELL == EXPECTED_FLOWCELL_API_BASE

            aviti_dir = tmpdir / "20261103_AV261102_261103_Seq00334_Seq00319_Seq00336"
            aviti_dir.mkdir()
            (aviti_dir / "RunParameters.json").write_text(
                json.dumps({"FlowcellID": "2533537859"}),
                encoding="utf-8",
            )
            raw_manifest = aviti_dir / "RunManifest.csv"
            raw_manifest.write_text("raw-manifest-must-not-be-used\n", encoding="utf-8")
            aviti_bundle = make_bundle(
                {
                    "run_manifest_aviti.csv": "api-aviti-manifest\n",
                    "sample-evidence.csv": "evidence\n",
                    "README.md": "# Review warnings\n",
                }
            )
            calls: list[str] = []

            def fetch_aviti_flowcell(url: str, auth_header: str) -> bytes:
                calls.append(url)
                assert auth_header == "Basic token"
                return aviti_bundle

            MODULE._build_auth_header = lambda: "Basic token"
            MODULE._fetch = fetch_aviti_flowcell
            ctx = FakeContext(
                tmpdir,
                platform="aviti",
                bcl_dir=str(aviti_dir),
                use_api_samplesheet=True,
            )
            resolved = Path(MODULE.resolve(ctx))
            assert resolved.name == "run_manifest_aviti.csv"
            assert resolved.read_text(encoding="utf-8") == "api-aviti-manifest\n"
            assert resolved != raw_manifest.resolve()
            assert calls == [f"{EXPECTED_FLOWCELL_API_BASE}2533537859"]
            assert (resolved.parent / "bundle.zip").read_bytes() == aviti_bundle
            assert (resolved.parent / "sample-evidence.csv").read_text(encoding="utf-8") == "evidence\n"
            assert (resolved.parent / "README.md").read_text(encoding="utf-8") == "# Review warnings\n"
            assert len(ctx.warnings) == 1
            assert "2533537859" in str(ctx.warnings[0]["message"])
            assert "README.md" in str(ctx.warnings[0]["action"])

            illumina_bundle = make_bundle(
                {
                    "SampleSheet.csv": "[Header]\n",
                    "sample-evidence.csv": "evidence\n",
                    "README.md": "# Review\n",
                }
            )
            calls = []

            def fetch_illumina(url: str, auth_header: str) -> bytes:
                calls.append(url)
                return illumina_bundle

            MODULE._fetch = fetch_illumina
            ctx = FakeContext(
                tmpdir,
                platform="illumina",
                bcl_dir="/data/run/260407_NB501289_0992_AHLHGVBGYX",
                use_api_samplesheet=True,
            )
            resolved = Path(MODULE.resolve(ctx))
            assert resolved.name == "SampleSheet.csv"
            assert resolved.read_text(encoding="utf-8") == "[Header]\n"
            assert calls == [f"{EXPECTED_FLOWCELL_API_BASE}HLHGVBGYX"]

            MODULE._fetch = lambda url, auth: (_ for _ in ()).throw(
                MODULE.HTTPError(
                    url,
                    404,
                    "not found",
                    hdrs=None,
                    fp=io.BytesIO(b'{"detail":"flowcell not found"}'),
                )
            )
            ctx = FakeContext(
                tmpdir,
                platform="illumina",
                bcl_dir="/data/run/260407_NB501289_0992_AHLHGVBGYX",
                use_api_samplesheet=True,
            )
            expect_runtime_error(lambda: MODULE.resolve(ctx), "HTTP 404 flowcell not found")

            MODULE._fetch = lambda url, auth: b"not a zip"
            expect_runtime_error(lambda: MODULE.resolve(ctx), "invalid samplesheet ZIP bundle")

            MODULE._fetch = lambda url, auth: make_bundle(
                {
                    "../escape.csv": "bad\n",
                    "SampleSheet.csv": "sheet\n",
                }
            )
            expect_runtime_error(lambda: MODULE.resolve(ctx), "Unsafe path")
            assert not (tmpdir / "escape.csv").exists()

            MODULE._fetch = lambda url, auth: make_bundle(
                {
                    "first.csv": "one\n",
                    "second.csv": "two\n",
                    "sample-evidence.csv": "evidence\n",
                }
            )
            expect_runtime_error(lambda: MODULE.resolve(ctx), "Could not identify exactly one")

            MODULE.MAX_BUNDLE_UNCOMPRESSED_BYTES = 8
            MODULE._fetch = lambda url, auth: illumina_bundle
            expect_runtime_error(lambda: MODULE.resolve(ctx), "too large after decompression")
            MODULE.MAX_BUNDLE_UNCOMPRESSED_BYTES = original_max_bytes

            missing_parameters = tmpdir / "aviti-without-run-parameters"
            missing_parameters.mkdir()
            ctx = FakeContext(
                tmpdir,
                platform="aviti",
                bcl_dir=str(missing_parameters),
                use_api_samplesheet=True,
            )
            expect_runtime_error(lambda: MODULE.resolve(ctx), "RunParameters.json does not exist")

            ctx = FakeContext(
                tmpdir,
                platform="illumina",
                bcl_dir="/data/run/example",
                flowcell_id="../../escape",
                use_api_samplesheet=True,
            )
            expect_runtime_error(lambda: MODULE.resolve(ctx), "Unsafe or unsupported flowcell id")

            MODULE.MAX_BUNDLE_DOWNLOAD_BYTES = 8
            ctx = FakeContext(
                tmpdir,
                platform="illumina",
                bcl_dir="/data/run/260407_NB501289_0992_AHLHGVBGYX",
                use_api_samplesheet=True,
            )
            MODULE._fetch = lambda url, auth: illumina_bundle
            expect_runtime_error(lambda: MODULE.resolve(ctx), "bundle download exceeds")
            MODULE.MAX_BUNDLE_DOWNLOAD_BYTES = original_max_download

            MODULE._build_auth_header = lambda: (_ for _ in ()).throw(
                RuntimeError("missing credentials")
            )
            ctx = FakeContext(
                tmpdir,
                platform="illumina",
                bcl_dir="/data/run/260407_NB501289_0992_AHLHGVBGYX",
                use_api_samplesheet=True,
            )
            expect_runtime_error(lambda: MODULE.resolve(ctx), "missing credentials")
        finally:
            MODULE._fetch = original_fetch
            MODULE._build_auth_header = original_build_auth_header
            MODULE.MAX_BUNDLE_DOWNLOAD_BYTES = original_max_download
            MODULE.MAX_BUNDLE_UNCOMPRESSED_BYTES = original_max_bytes
            if original_linkar_home is None:
                os.environ.pop("LINKAR_HOME", None)
            else:
                os.environ["LINKAR_HOME"] = original_linkar_home

    print("get_api_samplesheet tests passed")


if __name__ == "__main__":
    main()
