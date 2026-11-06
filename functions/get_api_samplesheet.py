from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_FLOWCELL = os.environ.get(
    "GF_API_BASE_FLOWCELL",
    "https://genomics.rwth-aachen.de/api/get/samplesheet/flowcell/",
)
MAX_BUNDLE_FILES = 100
MAX_BUNDLE_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_BUNDLE_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
FLOWCELL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _nonempty(value: object | None) -> str:
    return str(value or "").strip()


def _truthy(value: object | None, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    text = _nonempty(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _aviti_flowcell_id(input_dir: str) -> str:
    run_parameters = Path(input_dir).expanduser() / "RunParameters.json"
    try:
        payload = json.loads(run_parameters.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Could not resolve the AVITI flowcell id: {run_parameters} does not exist"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read AVITI run parameters from {run_parameters}: {exc}") from exc

    flowcell_id = _nonempty(payload.get("FlowcellID")) if isinstance(payload, dict) else ""
    if not flowcell_id:
        raise RuntimeError(f"AVITI run parameters do not contain a non-empty FlowcellID: {run_parameters}")
    return flowcell_id


def _parse_flowcell_id(input_dir: str, *, platform: str = "") -> str | None:
    if platform.strip().lower() == "aviti":
        return _aviti_flowcell_id(input_dir)

    base = os.path.basename(os.path.normpath(input_dir or ""))
    if not base:
        return None
    parts = base.split("_")
    last = parts[-1] if parts else ""
    if not last:
        return None
    return last[1:] if len(last) >= 2 and last[0].isalpha() else last


def _validated_flowcell_id(value: str) -> str:
    if not FLOWCELL_ID_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise RuntimeError(f"Unsafe or unsupported flowcell id for API lookup: {value!r}")
    return value


def _build_auth_header() -> str:
    user = _nonempty(os.getenv("GF_API_NAME"))
    password = _nonempty(os.getenv("GF_API_PASS"))
    if not user or not password:
        raise RuntimeError("Missing GF_API_NAME/GF_API_PASS for API samplesheet lookup")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _extract_error_detail(exc: HTTPError) -> str | None:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        detail = _nonempty(payload.get("detail"))
        return detail or None
    return None


def _extract_not_found_detail(exc: HTTPError) -> str | None:
    """Backward-compatible helper used by the nfcore_demultiplex binding."""
    return _extract_error_detail(exc)


def _fetch(url: str, auth_header: str) -> bytes:
    request = Request(url, headers={"Authorization": auth_header, "Accept": "application/zip"})
    with urlopen(request, timeout=20) as response:
        content = response.read(MAX_BUNDLE_DOWNLOAD_BYTES + 1)
    if len(content) > MAX_BUNDLE_DOWNLOAD_BYTES:
        raise RuntimeError(
            f"GF API samplesheet bundle download exceeds {MAX_BUNDLE_DOWNLOAD_BYTES} bytes"
        )
    return content


def _cache_root() -> Path:
    linkar_home = _nonempty(os.getenv("LINKAR_HOME"))
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "api_samplesheets"
    return Path.home().resolve() / ".linkar" / "api_samplesheets"


def _fallback_template_samplesheet(ctx) -> str:
    fallback = Path(ctx.template.root) / "samplesheet.csv"
    if fallback.exists():
        return str(fallback.resolve())
    raise RuntimeError("API samplesheet lookup is disabled and no bundled samplesheet.csv exists")


def _input_dir_from_resolved(resolved: dict[str, object]) -> str:
    return _nonempty(resolved.get("input_dir")) or _nonempty(resolved.get("bcl_dir"))


def _validated_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    files = [info for info in archive.infolist() if not info.is_dir()]
    if not files:
        raise RuntimeError("API samplesheet bundle is empty")
    if len(files) > MAX_BUNDLE_FILES:
        raise RuntimeError(
            f"API samplesheet bundle contains too many files ({len(files)} > {MAX_BUNDLE_FILES})"
        )

    total_size = 0
    for info in files:
        member = PurePosixPath(info.filename)
        if member.is_absolute() or ".." in member.parts or not member.name:
            raise RuntimeError(f"Unsafe path in API samplesheet bundle: {info.filename!r}")
        unix_mode = info.external_attr >> 16
        if stat.S_ISLNK(unix_mode):
            raise RuntimeError(f"Symbolic links are not allowed in API samplesheet bundle: {info.filename!r}")
        if info.flag_bits & 0x1:
            raise RuntimeError(f"Encrypted files are not allowed in API samplesheet bundle: {info.filename!r}")
        total_size += info.file_size

    if total_size > MAX_BUNDLE_UNCOMPRESSED_BYTES:
        raise RuntimeError(
            "API samplesheet bundle is too large after decompression "
            f"({total_size} > {MAX_BUNDLE_UNCOMPRESSED_BYTES} bytes)"
        )
    return files


def _select_primary_member(files: list[zipfile.ZipInfo], *, platform: str) -> zipfile.ZipInfo:
    by_basename: dict[str, list[zipfile.ZipInfo]] = {}
    for info in files:
        by_basename.setdefault(PurePosixPath(info.filename).name.casefold(), []).append(info)

    if platform == "aviti":
        preferred_names = ("run_manifest_aviti.csv",)
    else:
        preferred_names = ("samplesheet.csv", "sample_sheet.csv", "samplesheet_illumina.csv")

    preferred = [info for name in preferred_names for info in by_basename.get(name, [])]
    if len(preferred) == 1:
        return preferred[0]
    if len(preferred) > 1:
        names = ", ".join(sorted(info.filename for info in preferred))
        raise RuntimeError(f"API samplesheet bundle contains multiple primary manifest candidates: {names}")

    csv_candidates = [
        info
        for info in files
        if PurePosixPath(info.filename).suffix.casefold() == ".csv"
        and "evidence" not in PurePosixPath(info.filename).name.casefold()
    ]
    if len(csv_candidates) == 1:
        return csv_candidates[0]

    names = ", ".join(sorted(info.filename for info in csv_candidates)) or "none"
    raise RuntimeError(
        f"Could not identify exactly one primary {platform or 'sequencing'} manifest in API bundle; "
        f"CSV candidates: {names}"
    )


def _cache_bundle(content: bytes, *, flowcell_id: str, platform: str) -> tuple[Path, Path | None]:
    if len(content) > MAX_BUNDLE_DOWNLOAD_BYTES:
        raise RuntimeError(
            f"GF API samplesheet bundle download exceeds {MAX_BUNDLE_DOWNLOAD_BYTES} bytes"
        )
    digest = hashlib.sha256(content).hexdigest()
    out_dir = _cache_root() / flowcell_id / digest
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files = _validated_members(archive)
            primary = _select_primary_member(files, platform=platform)
            for info in files:
                relative = PurePosixPath(info.filename)
                target = out_dir.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
    except zipfile.BadZipFile as exc:
        raise RuntimeError("GF API returned an invalid samplesheet ZIP bundle") from exc

    bundle_path = out_dir / "bundle.zip"
    bundle_path.write_bytes(content)
    primary_path = out_dir.joinpath(*PurePosixPath(primary.filename).parts).resolve()
    readme_candidates = [
        out_dir.joinpath(*PurePosixPath(info.filename).parts).resolve()
        for info in files
        if PurePosixPath(info.filename).name.casefold() == "readme.md"
    ]
    return primary_path, readme_candidates[0] if len(readme_candidates) == 1 else None


def _warn_for_review(ctx, *, flowcell_id: str, readme_path: Path | None) -> None:
    warn = getattr(ctx, "warn", None)
    if not callable(warn):
        return
    location = str(readme_path) if readme_path is not None else "the cached API bundle"
    warn(
        f"The GF API returned a review bundle for flowcell {flowcell_id}.",
        action=f"Review the manifest, evidence, and warnings in {location} before demultiplexing.",
    )


def resolve(ctx) -> str:
    resolved = dict(ctx.resolved_params or {})

    explicit_samplesheet = _nonempty(resolved.get("samplesheet"))
    if explicit_samplesheet:
        return explicit_samplesheet

    if not _truthy(resolved.get("use_api_samplesheet"), default=True):
        return _fallback_template_samplesheet(ctx)

    platform = _nonempty(resolved.get("platform")).lower()
    input_dir = _input_dir_from_resolved(resolved)
    if not input_dir:
        raise RuntimeError("API samplesheet lookup requires bcl_dir/input_dir or an explicit flowcell_id")

    flowcell_id = _nonempty(resolved.get("flowcell_id")) or (
        _parse_flowcell_id(input_dir, platform=platform) or ""
    )
    if not flowcell_id:
        raise RuntimeError("Could not resolve a flowcell id for API samplesheet lookup")
    flowcell_id = _validated_flowcell_id(flowcell_id)

    auth_header = _build_auth_header()
    target_url = f"{API_BASE_FLOWCELL}{flowcell_id}"
    try:
        content = _fetch(target_url, auth_header)
    except HTTPError as exc:
        detail = _extract_error_detail(exc) or exc.reason
        raise RuntimeError(
            f"GF API samplesheet bundle lookup failed for flowcell {flowcell_id}: "
            f"HTTP {exc.code} {detail}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"GF API samplesheet bundle lookup failed for flowcell {flowcell_id}: {exc.reason}"
        ) from exc

    primary_path, readme_path = _cache_bundle(
        content,
        flowcell_id=flowcell_id,
        platform=platform,
    )
    _warn_for_review(ctx, flowcell_id=flowcell_id, readme_path=readme_path)
    return str(primary_path)
