#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit an export request for an ad hoc demultiplex run.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--project-name", default="")
    parser.add_argument("--fastq-dir", default="")
    parser.add_argument("--multiqc-report", default="")
    parser.add_argument("--export-engine-api-url", default="http://genomics.rwth-aachen.de:9500/export")
    parser.add_argument("--export-engine-backends", default="apache, owncloud, sftp")
    parser.add_argument("--export-expiry-days", type=int, default=30)
    parser.add_argument("--export-username", default="")
    parser.add_argument("--export-password", default="")
    parser.add_argument("--include-in-report", default="true")
    parser.add_argument("--include-in-report-fastq", default="true")
    parser.add_argument("--include-in-report-multiqc", default="true")
    parser.add_argument("--poll-interval-seconds", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--dry-run", default="false")
    return parser.parse_args()


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


def split_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def derive_username(project_name: str) -> str:
    parts = project_name.split("_")
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return project_name or "user"


def default_project_name(run_dir: Path) -> str:
    base = run_dir.name.strip()
    if not base:
        return "adhoc_demultiplex_export_run_data"
    parts = [part for part in base.split("_") if part]
    if len(parts) == 5:
        return base
    if len(parts) == 4:
        return f"{base}_demultiplex"
    while len(parts) < 5:
        parts.append("demultiplex")
    return "_".join(parts[:5])


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def supports_spinner() -> bool:
    term = os.environ.get("TERM", "")
    return sys.stdout.isatty() and term.lower() != "dumb"


def ansi(code: str) -> str:
    return f"\033[{code}m" if supports_color() else ""


RESET = ansi("0")
BOLD = ansi("1")
BLUE = ansi("34")
CYAN = ansi("36")
GREEN = ansi("32")
YELLOW = ansi("33")


def color(text: str, tone: str, *, bold: bool = False) -> str:
    prefix = f"{BOLD if bold else ''}{tone}"
    return f"{prefix}{text}{RESET}" if prefix else text


def print_section(title: str, tone: str = CYAN) -> None:
    line = "=" * 72
    print(color(line, tone))
    print(color(title, tone, bold=True))
    print(color(line, tone))


def print_key_value(label: str, value: str, *, tone: str = BLUE) -> None:
    print(f"{color(label + ':', tone, bold=True)} {value}")


def run_with_spinner(message: str, func):
    if not supports_spinner():
        print(message)
        return func()

    stop_event = threading.Event()
    spinner = ["|", "/", "-", "\\"]

    def spin() -> None:
        idx = 0
        while not stop_event.is_set():
            sys.stdout.write(f"\r{message} {spinner[idx % len(spinner)]}")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.2)
        sys.stdout.write("\r" + " " * (len(message) + 2) + "\r")
        sys.stdout.flush()

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    try:
        return func()
    finally:
        stop_event.set()
        thread.join()


def split_hostpath(raw: str, default_host: str) -> tuple[str, str]:
    if ":" in raw:
        host, rest = raw.split(":", 1)
        if host and rest.startswith("/"):
            return host, rest
    return default_host, raw


def resolve_input_path(raw: str | Path, run_dir: Path, default_host: str) -> tuple[str, Path]:
    if isinstance(raw, Path):
        return default_host, raw
    host, path = split_hostpath(str(raw), default_host)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (run_dir / candidate).resolve()
    return host, candidate


def auto_link_name(path: str, dest: str) -> str:
    name = Path(dest).name if path == "." else Path(path).name
    return name.replace("_", " ").strip()


def export_entry(
    src_path: Path,
    dest_path: str,
    export_host: str,
    project_name: str,
    include_report: bool,
    description: str,
) -> dict:
    entry = {
        "src": str(src_path.resolve()),
        "dest": dest_path,
        "host": export_host,
        "project": project_name,
        "mode": "symlink",
    }
    if include_report:
        entry["report_links"] = [
            {
                "path": ".",
                "section": "raw",
                "description": description,
                "link_name": auto_link_name(".", dest_path),
            }
        ]
    return entry


def export_metadata_paths(run_dir: Path) -> tuple[Path, Path]:
    root = run_dir / ".linkar" / "export_demux"
    attempt_dir = root / now_stamp()
    latest_dir = root / "latest"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    return attempt_dir, latest_dir


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sync_latest(attempt_dir: Path, latest_dir: Path) -> None:
    for child in latest_dir.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
    for item in attempt_dir.iterdir():
        if item.is_file():
            write_text(latest_dir / item.name, item.read_text(encoding="utf-8"))


def strip_markdown(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"[*`#]+", "", cleaned)
    cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", cleaned)
    return cleaned.strip()


def normalize_summary_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def build_final_summary(final_json: dict[str, object]) -> str:
    formatted = strip_markdown(str(final_json.get("formatted_message") or ""))
    raw = str(final_json.get("message") or "").strip()
    if formatted and raw:
        if normalize_summary_text(formatted) == normalize_summary_text(raw):
            return formatted
        return f"{formatted}\n\nRaw API Message\n\n{raw}"
    return formatted or raw


def final_pending(exc: HTTPError, detail: str) -> bool:
    if exc.code == 425:
        return True
    if exc.code == 404 and "Job not found" in detail:
        return True
    return False


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        raise SystemExit(f"run_dir not found or not a directory: {run_dir}")

    project_name = args.project_name.strip() or default_project_name(run_dir)
    host_default = os.uname().nodename.split(".")[0]

    fastq_raw = args.fastq_dir.strip() or str(run_dir / "output")
    multiqc_raw = args.multiqc_report.strip() or str(run_dir / "multiqc" / "multiqc_report.html")
    fastq_host, fastq_dir = resolve_input_path(fastq_raw, run_dir, host_default)
    multiqc_host, multiqc_report = resolve_input_path(multiqc_raw, run_dir, host_default)

    if fastq_host == host_default and not fastq_dir.exists():
        raise SystemExit(f"FASTQ dir not found: {fastq_dir}")
    if multiqc_host == host_default and not multiqc_report.exists():
        raise SystemExit(f"MultiQC report not found: {multiqc_report}")

    include_default = parse_bool(args.include_in_report, True)
    include_fastq = parse_bool(args.include_in_report_fastq, include_default)
    include_multiqc = parse_bool(args.include_in_report_multiqc, include_default)
    username = args.export_username.strip() or derive_username(project_name)
    password = args.export_password.strip() or secrets.token_urlsafe(16)

    export_list = [
        export_entry(
            fastq_dir,
            "1_Raw_data/FASTQ",
            fastq_host,
            project_name,
            include_fastq,
            "FASTQ output from demultiplex",
        ),
        export_entry(
            multiqc_report,
            "1_Raw_data/demultiplexing_multiqc_report.html",
            multiqc_host,
            project_name,
            include_multiqc,
            "MultiQC report from demultiplex",
        ),
    ]

    job_spec = {
        "project_name": project_name,
        "export_list": export_list,
        "backend": split_csv(args.export_engine_backends),
        "username": username,
        "password": password,
        "authors": [],
        "expiry_days": int(args.export_expiry_days or 0),
    }

    redacted_spec = json.loads(json.dumps(job_spec))
    redacted_spec["password"] = "***redacted***"

    attempt_dir, latest_dir = export_metadata_paths(run_dir)
    write_json(attempt_dir / "export_job_spec.json", job_spec)
    write_json(attempt_dir / "export_job_spec.redacted.json", redacted_spec)

    if parse_bool(args.dry_run, False):
        sync_latest(attempt_dir, latest_dir)
        write_text(results_dir / "export_metadata_dir.txt", str(latest_dir) + "\n")
        print_section("Dry Run", YELLOW)
        print_key_value("run_dir", str(run_dir))
        print_key_value("canonical metadata", str(latest_dir))
        print_key_value("job spec", str(latest_dir / "export_job_spec.redacted.json"))
        return 0

    api_clean = args.export_engine_api_url.rstrip("/")
    export_endpoint = api_clean if api_clean.endswith("/export") else f"{api_clean}/export"
    req = Request(
        export_endpoint,
        data=json.dumps(job_spec).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        def post_request():
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")

        body = run_with_spinner("Submitting export job", post_request)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise SystemExit(f"Export API request failed: {exc.code} {detail}")
    except URLError as exc:
        raise SystemExit(f"Export API request failed: {exc.reason}")

    try:
        response_json = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Export API returned non-JSON response: {exc}") from exc
    if not isinstance(response_json, dict):
        raise SystemExit("Export API returned a non-object response")
    job_id = str(response_json.get("job_id") or "").strip()
    if not job_id:
        raise SystemExit("Export API response missing job_id")
    write_json(attempt_dir / "export_response.json", response_json)

    final_endpoint = (
        f"{api_clean}/final_message/{job_id}"
        if api_clean.endswith("/export")
        else f"{api_clean}/export/final_message/{job_id}"
    )
    final_req = Request(final_endpoint, method="GET")

    def wait_for_final():
        start = time.monotonic()
        while True:
            if time.monotonic() - start > max(1, int(args.timeout_seconds)):
                raise TimeoutError(f"Timed out waiting for final export status for job_id={job_id}")
            try:
                with urlopen(final_req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8") if exc.fp else str(exc)
                if final_pending(exc, detail):
                    time.sleep(max(1, int(args.poll_interval_seconds)))
                    continue
                raise RuntimeError(f"Unable to fetch final message: {exc.code} {detail}") from exc
            except URLError:
                time.sleep(max(1, int(args.poll_interval_seconds)))
                continue

    try:
        final_json = run_with_spinner("Waiting for final export status", wait_for_final)
    except Exception as exc:
        raise SystemExit(str(exc)) from exc

    write_json(attempt_dir / "export_final_message.json", final_json)
    write_text(attempt_dir / "export_job_id.txt", job_id + "\n")
    final_path = str(final_json.get("final_path") or "").strip()
    write_text(attempt_dir / "export_final_path.txt", final_path + ("\n" if final_path else ""))

    sync_latest(attempt_dir, latest_dir)
    write_text(results_dir / "export_metadata_dir.txt", str(latest_dir) + "\n")
    write_text(results_dir / "export_job_id.txt", job_id + "\n")

    print_section("Export Request", BLUE)
    print_key_value("API endpoint", export_endpoint)
    print_key_value("Project", project_name)
    print_key_value("Source run_dir", str(run_dir))
    print_key_value("Canonical metadata", str(latest_dir))
    print_section("Job Registered", GREEN)
    print_key_value("job_id", job_id, tone=GREEN)
    if final_path:
        print_key_value("final_path", final_path, tone=GREEN)
    if final_json.get("main_report"):
        print_key_value("report", str(final_json["main_report"]), tone=GREEN)
    if final_json.get("formatted_message") or final_json.get("message"):
        print("")
        print_section("Final Export Summary", CYAN)
        print(build_final_summary(final_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
