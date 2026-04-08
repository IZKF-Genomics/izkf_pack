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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit an export request for a raw BCL run.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--project-name", default="")
    parser.add_argument("--bcl-dir", default="")
    parser.add_argument("--include-in-report", default="true")
    parser.add_argument("--include-in-report-bcl", default="true")
    parser.add_argument("--export-engine-api-url", default="http://genomics.rwth-aachen.de:9500/export")
    parser.add_argument("--export-engine-backends", default="apache, owncloud, sftp")
    parser.add_argument("--export-expiry-days", type=int, default=30)
    parser.add_argument("--export-username", default="")
    parser.add_argument("--export-password", default="")
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


def strip_markdown(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"[*`#]+", "", cleaned)
    cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", cleaned)
    return cleaned.strip()


def parse_raw_api_message(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip().rstrip(",")
        if not stripped:
            continue
        match = re.match(r"^'([^']+)':\s*(.*)$", stripped)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        parsed[key] = value
    return parsed


def print_list_item(label: str, value: str) -> None:
    print(f"- {label}: {value}")


def print_final_export_summary(final_json: dict[str, object]) -> None:
    print_section("Final Export Summary", CYAN)
    print("Export complete.")

    main_report = str(final_json.get("main_report") or "").strip()
    username = str(final_json.get("username") or "").strip()
    password = str(final_json.get("password") or "").strip()

    if main_report:
        print("")
        print("Main Report")
        print_list_item("URL", main_report)

    if username or password:
        print("")
        print("Access Credentials")
        if username:
            print_list_item("Username", username)
        if password:
            print_list_item("Password", password)

    publisher_results = final_json.get("publisher_results")
    if isinstance(publisher_results, list) and publisher_results:
        print("")
        print("Publisher Results")
        for index, publisher in enumerate(publisher_results, start=1):
            if not isinstance(publisher, dict):
                continue
            publisher_name = str(publisher.get("publisher") or f"publisher {index}").upper()
            print(f"{index}. {publisher_name}")
            url = str(publisher.get("url") or "").strip()
            publisher_username = str(publisher.get("username") or "").strip()
            publisher_password = str(publisher.get("password") or "").strip()
            if url:
                print_list_item("URL", url)
            if publisher_username:
                print_list_item("Username", publisher_username)
            if publisher_password:
                print_list_item("Password", publisher_password)

    raw_message = str(final_json.get("message") or "").strip()
    raw_fields = parse_raw_api_message(raw_message)
    if raw_fields:
        planner_patch = {
            "Project ID": raw_fields.get("Project ID", ""),
            "Report URL": raw_fields.get("Report URL", ""),
            "Username": raw_fields.get("Username", ""),
            "Password": raw_fields.get("Password", ""),
            "Download URL": raw_fields.get("Download URL", ""),
            "Download command": raw_fields.get("Download command", ""),
        }
        print("")
        print_section("JSON Patch for MS Planner", YELLOW)
        print(json.dumps(planner_patch, indent=2))


def final_pending(exc: HTTPError, detail: str) -> bool:
    if exc.code == 425:
        return True
    if exc.code == 404 and "Job not found" in detail:
        return True
    return False


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        raise SystemExit(f"run_dir not found or not a directory: {run_dir}")

    project_name = args.project_name.strip() or run_dir.name
    bcl_dir = Path(args.bcl_dir).expanduser().resolve() if args.bcl_dir.strip() else run_dir
    if not bcl_dir.exists():
        raise SystemExit(f"BCL dir not found: {bcl_dir}")

    include_default = parse_bool(args.include_in_report, True)
    include_bcl = parse_bool(args.include_in_report_bcl, include_default)
    username = args.export_username.strip() or derive_username(project_name)
    password = args.export_password.strip() or secrets.token_urlsafe(16)
    host = os.uname().nodename.split(".")[0]

    export_list = [
        {
            "src": str(bcl_dir.resolve()),
            "dest": "BCL",
            "host": host,
            "project": project_name,
            "mode": "symlink",
            "include_in_report": include_bcl,
            "report_section": "raw",
            "description": "Raw BCL run directory",
        }
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
    write_json(results_dir / "export_job_spec.json", job_spec)
    write_json(results_dir / "export_job_spec.redacted.json", redacted_spec)

    summary = {
        "run_dir": str(run_dir),
        "bcl_dir": str(bcl_dir),
        "project_name": project_name,
        "dry_run": parse_bool(args.dry_run, False),
        "export_engine_api_url": args.export_engine_api_url,
    }

    if parse_bool(args.dry_run, False):
        write_json(results_dir / "export_bcl_summary.json", summary)
        print_section("Dry Run", YELLOW)
        print_key_value("run_dir", str(run_dir))
        print_key_value("bcl_dir", str(bcl_dir))
        print_key_value("job spec", str(results_dir / "export_job_spec.redacted.json"))
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

    response_json = json.loads(body)
    if not isinstance(response_json, dict):
        raise SystemExit("Export API returned a non-object response")
    job_id = str(response_json.get("job_id") or "").strip()
    if not job_id:
        raise SystemExit("Export API response missing job_id")
    write_json(results_dir / "export_response.json", response_json)

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

    final_json = run_with_spinner("Waiting for final export status", wait_for_final)
    write_json(results_dir / "export_final_message.json", final_json)
    write_text(results_dir / "export_job_id.txt", job_id + "\n")

    summary.update(
        {
            "job_id": job_id,
            "status": str(final_json.get("status") or final_json.get("type") or ""),
            "final_path": str(final_json.get("final_path") or ""),
            "main_report": str(final_json.get("main_report") or ""),
        }
    )
    write_json(results_dir / "export_bcl_summary.json", summary)

    print_section("Export Request", BLUE)
    print_key_value("API endpoint", export_endpoint)
    print_key_value("Project", project_name)
    print_key_value("BCL directory", str(bcl_dir))
    print_section("Job Registered", GREEN)
    print_key_value("job_id", job_id, tone=GREEN)
    if final_json.get("main_report"):
        print_key_value("report", str(final_json["main_report"]), tone=GREEN)
    if final_json.get("final_path"):
        print_key_value("final_path", str(final_json["final_path"]), tone=GREEN)
    if final_json.get("formatted_message") or final_json.get("message"):
        print("")
        print_final_export_summary(final_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
