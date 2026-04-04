#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import csv
import fnmatch
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


RUN_PREFIX_RE = re.compile(r"^(?P<prefix>\d{6})_")
DEFAULT_MANIFEST_DIR = "/data/shared/linkar_manifests"
DEFAULT_INSTRUMENTS = [
    "miseq1_M00818",
    "miseq2_M04404",
    "miseq3_M00403",
    "nextseq500_NB501289",
    "novaseq_A01742",
]
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


@dataclass(frozen=True)
class ArchiveProfile:
    template_id: str
    source_root: str
    target_root: str
    manifest_prefix: str
    layout: str
    cleanup_allowed: bool
    exclude_patterns: tuple[str, ...]


@dataclass
class RunCandidate:
    run_id: str
    source_path: Path
    target_parent_path: Path
    target_path: Path
    run_date: date
    owner_user: str
    project_id: str | None
    size_bytes: int
    skipped: bool = False


def style(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def title(text: str) -> str:
    return style(text, "1;36")


def ok(text: str) -> str:
    return style(text, "1;32")


def warn(text: str) -> str:
    return style(text, "1;33")


def err(text: str) -> str:
    return style(text, "1;31")


def dim(text: str) -> str:
    return style(text, "2")


def cmd(text: str) -> str:
    return style(text, "36")


def print_section(text: str) -> None:
    print("\n" + title("=" * 80))
    print(title(text))
    print(title("=" * 80))


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_int(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def split_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def format_bytes(num_bytes: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def parse_run_date(run_id: str) -> date | None:
    match = RUN_PREFIX_RE.match(run_id)
    if not match:
        return None
    prefix = match.group("prefix")
    try:
        return date(2000 + int(prefix[:2]), int(prefix[2:4]), int(prefix[4:6]))
    except ValueError:
        return None


def parse_exported_at_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def owner_user(path: Path) -> str:
    try:
        return pwd.getpwuid(path.stat().st_uid).pw_name
    except Exception:
        return "unknown"


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def nested_get(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def project_name_from_ini(path: Path) -> str | None:
    ini_path = path / "project.ini"
    if not ini_path.is_file():
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(ini_path, encoding="utf-8")
    except Exception:
        return None
    if not parser.has_section("Project"):
        return None
    value = parser.get("Project", "project_name", fallback="").strip()
    return value or None


def sample_project_from_samplesheet(path: Path) -> str | None:
    for filename in ("samplesheet.csv", "samplesheet_bclconvert.csv"):
        samplesheet = path / filename
        if not samplesheet.is_file():
            continue
        current_section: str | None = None
        try:
            with samplesheet.open("r", encoding="utf-8", newline="") as fh:
                for raw_line in fh:
                    row = next(csv.reader([raw_line]))
                    first = row[0].strip() if row else ""
                    if not first:
                        continue
                    if first.startswith("[") and first.endswith("]"):
                        current_section = first[1:-1].strip()
                        continue
                    if current_section not in {"BCLConvert_Data", "Data"}:
                        continue
                    try:
                        project_idx = row.index("Sample_Project")
                    except ValueError:
                        return None
                    for data_line in fh:
                        data_row = next(csv.reader([data_line]))
                        first = data_row[0].strip() if data_row else ""
                        if not first:
                            continue
                        if first.startswith("[") and first.endswith("]"):
                            return None
                        if project_idx >= len(data_row):
                            continue
                        project_name = data_row[project_idx].strip()
                        if project_name:
                            return project_name
                    return None
        except Exception:
            return None
    return None


def project_id_from_folder(path: Path) -> str | None:
    bpm_meta = load_yaml_file(path / "bpm.meta.yaml")
    project_name = nested_get(bpm_meta, "export", "demux", "project_name")
    if isinstance(project_name, str) and project_name.strip():
        return project_name.strip()
    export_job_spec = load_json_file(path / "export_job_spec.json")
    project_name = export_job_spec.get("project_name")
    if isinstance(project_name, str) and project_name.strip():
        return project_name.strip()
    project_name = sample_project_from_samplesheet(path)
    if isinstance(project_name, str) and project_name.strip():
        return project_name.strip()
    project_name = project_name_from_ini(path)
    if isinstance(project_name, str) and project_name.strip():
        return project_name.strip()
    project_meta = load_yaml_file(path / "project.yaml")
    project_name = project_meta.get("name")
    if isinstance(project_name, str) and project_name.strip():
        return project_name.strip()
    return None


def get_retention_reference(path: Path, run_date: date) -> tuple[date, str]:
    meta_path = path / "bpm.meta.yaml"
    if not meta_path.exists():
        return run_date, "run_name_prefix"
    meta = load_yaml_file(meta_path)
    export = meta.get("export") or {}
    for key_path in (("last_exported_at",), ("demux", "last_exported_at")):
        current: Any = export
        for key in key_path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        parsed = parse_exported_at_date(current)
        if parsed is not None:
            return parsed, "export_last_exported_at"
    return run_date, "run_name_prefix"


def dir_size_bytes(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def compute_cutoff(retention_days: int) -> date:
    return date.today() - timedelta(days=retention_days)


def discover_candidates(
    profile: ArchiveProfile,
    source_root: Path,
    target_root: Path,
    retention_days: int,
    instruments: list[str],
    skip_runs: set[str],
) -> tuple[list[RunCandidate], list[str]]:
    candidates: list[RunCandidate] = []
    issues: list[str] = []
    cutoff = compute_cutoff(retention_days)

    if profile.layout == "instrument":
        for instrument in instruments:
            src_instrument = source_root / instrument
            dst_instrument = target_root / instrument
            if not src_instrument.exists() or not src_instrument.is_dir():
                issues.append(f"Missing source instrument directory: {src_instrument}")
                continue
            for entry in sorted(src_instrument.iterdir()):
                if not entry.is_dir():
                    continue
                run_date = parse_run_date(entry.name)
                if run_date is None:
                    continue
                ref_date, _ = get_retention_reference(entry, run_date)
                if ref_date >= cutoff or entry.name in skip_runs:
                    continue
                candidates.append(
                    RunCandidate(
                        run_id=entry.name,
                        source_path=entry,
                        target_parent_path=dst_instrument,
                        target_path=dst_instrument / entry.name,
                        run_date=run_date,
                        owner_user=owner_user(entry),
                        project_id=project_id_from_folder(entry),
                        size_bytes=dir_size_bytes(entry),
                    )
                )
    else:
        for entry in sorted(source_root.iterdir()):
            if not entry.is_dir():
                continue
            run_date = parse_run_date(entry.name)
            if run_date is None:
                continue
            ref_date, _ = get_retention_reference(entry, run_date)
            if ref_date >= cutoff or entry.name in skip_runs:
                continue
            candidates.append(
                RunCandidate(
                    run_id=entry.name,
                    source_path=entry,
                    target_parent_path=target_root,
                    target_path=target_root / entry.name,
                    run_date=run_date,
                    owner_user=owner_user(entry),
                    project_id=project_id_from_folder(entry),
                    size_bytes=dir_size_bytes(entry),
                )
            )

    candidates.sort(key=lambda item: (item.run_date, item.run_id))
    return candidates, issues


def print_plan(profile: ArchiveProfile, candidates: list[RunCandidate], retention_days: int, skip_runs: set[str]) -> None:
    cutoff = compute_cutoff(retention_days)
    print_section("Archive Plan")
    print(f"Workflow: {profile.template_id}")
    print(f"Retention days: {retention_days}")
    print(f"Archive runs older than: {cutoff.isoformat()} (strictly before this date)")
    print(f"Runs skipped by user: {', '.join(sorted(skip_runs)) if skip_runs else '(none)'}")
    if not candidates:
        print("\nNo run directories match the archive criteria.")
        return
    run_col = max(32, min(50, max(len(c.run_id) for c in candidates) + 2))
    owner_col = max(8, min(14, max(len(c.owner_user) for c in candidates) + 2))
    row_fmt = f"{{no:>4}}  {{run:<{run_col}}}{{owner:<{owner_col}}}{{size:>12}}"
    header = row_fmt.format(no="No.", run="Run ID", owner="Owner", size="Size")
    print("\nSelected runs:")
    print(dim(header))
    print(dim("-" * len(header)))
    for idx, item in enumerate(candidates, start=1):
        print(
            row_fmt.format(
                no=f"{idx}.",
                run=item.run_id,
                owner=item.owner_user,
                size=format_bytes(item.size_bytes),
            )
        )
    print("\nSummary:")
    print(ok(f"- Selected run count: {len(candidates)}"))
    print(ok(f"- Total size: {format_bytes(sum(item.size_bytes for item in candidates))}"))


def input_yes_no(prompt: str, default_yes: bool = False) -> bool:
    suffix = "Y/n" if default_yes else "y/N"
    answer = input(title(f"{prompt} [{suffix}]: ")).strip().lower()
    if not answer:
        return default_yes
    return answer in {"y", "yes"}


def assert_writable_dir(path: Path, create: bool = False) -> None:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise SystemExit(f"Directory missing or not a directory: {path}")
    if not os.access(path, os.W_OK | os.X_OK):
        raise SystemExit(f"No write permission for directory: {path}")
    try:
        with tempfile.NamedTemporaryFile(prefix=".linkar_archive_write_test_", dir=path, delete=True):
            pass
    except Exception as exc:
        raise SystemExit(f"Cannot write to directory {path}: {exc}") from exc


def ensure_target_free_space(target_root: Path, required_bytes: int, min_free_gb: int) -> None:
    usage = shutil.disk_usage(target_root)
    free_bytes = usage.free
    min_free_bytes = min_free_gb * 1024 * 1024 * 1024
    if free_bytes < min_free_bytes:
        raise SystemExit(
            f"Insufficient free space on {target_root}: {format_bytes(free_bytes)} free, "
            f"requires at least {format_bytes(min_free_bytes)}"
        )
    if required_bytes > free_bytes:
        raise SystemExit(
            f"Insufficient free space on {target_root}: need {format_bytes(required_bytes)}, "
            f"but only {format_bytes(free_bytes)} free"
        )


def preflight_paths(manifest_path: Path, log_path: Path, target_root: Path, candidates: list[RunCandidate]) -> None:
    assert_writable_dir(manifest_path.parent, create=True)
    assert_writable_dir(log_path.parent, create=True)
    assert_writable_dir(target_root)
    seen: set[Path] = set()
    for candidate in candidates:
        parent = candidate.target_parent_path
        if parent in seen:
            continue
        assert_writable_dir(parent, create=True)
        seen.add(parent)


def run_cmd(command: list[str]) -> None:
    print(cmd("+ " + " ".join(command)))
    subprocess.run(command, check=True)


def rsync_copy(candidate: RunCandidate, exclude_patterns: tuple[str, ...]) -> None:
    command = [
        "rsync",
        "-a",
        "--human-readable",
        "--info=progress2",
        "--no-inc-recursive",
        "--partial",
    ]
    for pattern in exclude_patterns:
        command.extend(["--exclude", pattern])
    command.extend([str(candidate.source_path), str(candidate.target_parent_path)])
    run_cmd(command)


def rsync_verify(candidate: RunCandidate, exclude_patterns: tuple[str, ...]) -> None:
    command = ["rsync", "-avhn", "--delete"]
    for pattern in exclude_patterns:
        command.extend(["--exclude", pattern])
    command.extend([f"{candidate.source_path}/", f"{candidate.target_path}/"])
    verify = subprocess.run(command, check=True, text=True, capture_output=True)
    lines = [line for line in verify.stdout.splitlines() if line.strip()]
    payload_lines = [line for line in lines if not line.startswith(("sending ", "sent ", "total size is "))]
    if payload_lines:
        raise RuntimeError(f"Verification mismatch after copy for {candidate.run_id}.")


def remove_source(candidate: RunCandidate) -> None:
    shutil.rmtree(candidate.source_path)


def append_log(log_path: Path, message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def manifest_payload(metadata: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    return {**metadata, "updated_at": datetime.now().isoformat(timespec="seconds"), "records": records}


def write_manifest(path: Path, metadata: dict[str, Any], records: list[dict[str, Any]]) -> None:
    write_json(path, manifest_payload(metadata, records))


def parse_args(profile: ArchiveProfile) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Archive workflow for {profile.template_id}.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--source-root", default=profile.source_root)
    parser.add_argument("--target-root", default=profile.target_root)
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument("--instrument-folders", default=",".join(DEFAULT_INSTRUMENTS))
    parser.add_argument("--skip-runs", default="")
    parser.add_argument("--yes", default="false")
    parser.add_argument("--non-interactive", default="false")
    parser.add_argument("--dry-run", default="false")
    parser.add_argument("--cleanup", default="true" if profile.cleanup_allowed else "false")
    parser.add_argument("--min-free-gb", type=int, default=500)
    parser.add_argument("--manifest-path", default="")
    parser.add_argument("--manifest-dir", default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--exclude-patterns", default=",".join(profile.exclude_patterns))
    return parser.parse_args()


def execute(profile: ArchiveProfile) -> int:
    args = parse_args(profile)
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    source_root = Path(args.source_root).expanduser().resolve()
    target_root = Path(args.target_root).expanduser().resolve()
    retention_days = parse_int(args.retention_days, 90)
    instruments = split_csv(args.instrument_folders) or list(DEFAULT_INSTRUMENTS)
    skip_runs = set(split_csv(args.skip_runs))
    yes = parse_bool(args.yes, False)
    non_interactive = parse_bool(args.non_interactive, False)
    dry_run = parse_bool(args.dry_run, False)
    cleanup = parse_bool(args.cleanup, False)
    if cleanup and not profile.cleanup_allowed:
        raise SystemExit(f"{profile.template_id} does not support cleanup.")
    if non_interactive:
        yes = True
        print(dim("[mode] non_interactive=true -> global confirmation auto-approved"))

    manifest_dir = Path(args.manifest_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = Path(args.manifest_path).expanduser().resolve() if str(args.manifest_path).strip() else manifest_dir / f"{profile.manifest_prefix}_{timestamp}.json"
    log_path = manifest_path.parent / f"{manifest_path.stem}.log"
    exclude_patterns = tuple(split_csv(args.exclude_patterns) or list(profile.exclude_patterns))

    if not source_root.exists() or not source_root.is_dir():
        raise SystemExit(f"Source root not found or not a directory: {source_root}")
    if not target_root.exists() or not target_root.is_dir():
        raise SystemExit(f"Target root not found or not a directory: {target_root}")

    candidates, issues = discover_candidates(profile, source_root, target_root, retention_days, instruments, skip_runs)
    print_section("Path Confirmation")
    print(f"Source root: {source_root}")
    print(f"Target root: {target_root}")
    print(f"Manifest path: {manifest_path}")
    print(f"Log path: {log_path}")
    print(f"Exclude patterns: {', '.join(exclude_patterns) if exclude_patterns else '(none)'}")

    if issues:
        print_section("Discovery Notes")
        for issue in issues:
            print(warn(f"- {issue}"))

    print_plan(profile, candidates, retention_days, skip_runs)

    preflight_paths(manifest_path, log_path, target_root, candidates)
    required_bytes = sum(item.size_bytes for item in candidates)
    ensure_target_free_space(target_root, required_bytes, args.min_free_gb)

    if candidates and not yes:
        if not sys.stdin.isatty():
            raise SystemExit("Global confirmation required. Re-run with --yes.")
        if not input_yes_no("Proceed with archive/copy/verify sequence for all selected runs?", default_yes=False):
            raise SystemExit("Aborted by user.")

    metadata = {
        "workflow": profile.template_id,
        "source_root": str(source_root),
        "target_root": str(target_root),
        "manifest_path": str(manifest_path),
        "log_path": str(log_path),
        "retention_days": retention_days,
        "dry_run": dry_run,
        "cleanup": cleanup,
        "exclude_patterns": list(exclude_patterns),
        "selected_count": len(candidates),
    }
    records: list[dict[str, Any]] = []
    write_manifest(manifest_path, metadata, records)

    for candidate in candidates:
        record = {
            "run_id": candidate.run_id,
            "source_path": str(candidate.source_path),
            "target_path": str(candidate.target_path),
            "owner_user": candidate.owner_user,
            "project_id": candidate.project_id,
            "run_date": candidate.run_date.isoformat(),
            "size_bytes": candidate.size_bytes,
            "copy_status": "pending",
            "verify_status": "pending",
            "cleanup_status": "not_requested",
            "status": "pending",
            "error": "",
        }
        records.append(record)
        try:
            if dry_run:
                record["copy_status"] = "skipped_dry_run"
                record["verify_status"] = "skipped_dry_run"
                record["cleanup_status"] = "skipped_dry_run"
                record["status"] = "dry_run_only"
                append_log(log_path, f"{candidate.run_id}: dry run only")
                write_manifest(manifest_path, metadata, records)
                continue

            rsync_copy(candidate, exclude_patterns)
            record["copy_status"] = "completed"
            append_log(log_path, f"{candidate.run_id}: copy completed")
            write_manifest(manifest_path, metadata, records)

            rsync_verify(candidate, exclude_patterns)
            record["verify_status"] = "completed"
            append_log(log_path, f"{candidate.run_id}: verify completed")

            if cleanup:
                remove_source(candidate)
                record["cleanup_status"] = "completed"
                append_log(log_path, f"{candidate.run_id}: cleanup completed")
            record["status"] = "completed"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            append_log(log_path, f"{candidate.run_id}: failed: {exc}")
            write_manifest(manifest_path, metadata, records)
            raise
        write_manifest(manifest_path, metadata, records)

    print_section("Archive Summary")
    completed = sum(1 for record in records if record["status"] == "completed")
    dry_only = sum(1 for record in records if record["status"] == "dry_run_only")
    print(ok(f"Completed runs: {completed}"))
    if dry_only:
        print(warn(f"Dry-run only: {dry_only}"))
    print(ok(f"Manifest: {manifest_path}"))
    print(ok(f"Log: {log_path}"))

    write_text(results_dir / "manifest_path.txt", str(manifest_path) + "\n")
    write_text(results_dir / "log_path.txt", str(log_path) + "\n")
    return 0
