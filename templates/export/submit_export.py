#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from export_common import save_private_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit a prepared export_job_spec.json to the export engine.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results-dir", default="./results", help="Directory containing export_job_spec.json.")
    parser.add_argument("--api-url", required=True, help="Base URL of the export engine; /export is appended if needed.")
    parser.add_argument("--refresh", default="false", help="Refresh an existing export job instead of creating a new one.")
    parser.add_argument("--job-id", default="", help="Existing export job id for refresh; falls back to saved state.")
    parser.add_argument("--poll-interval-seconds", type=int, default=2, help="Poll interval for GET /export/{job_id}/poll.")
    parser.add_argument("--timeout-seconds", type=int, default=3600, help="Timeout while polling for final export status.")
    parser.add_argument("--show-password", default="true", help="Print passwords in terminal output; set false to redact them. Saved public artifacts remain redacted.")
    return parser.parse_args()


def endpoint(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    return base if base.endswith("/export") else f"{base}/export"


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


def refresh_endpoint(export_url: str, job_id: str) -> str:
    return f"{export_url}/{job_id}/refresh"


def poll_endpoint(export_url: str, job_id: str) -> str:
    return f"{export_url}/{job_id}/poll"


def final_message_endpoint(export_url: str, job_id: str) -> str:
    if export_url.endswith("/export"):
        return f"{export_url.rsplit('/export', 1)[0]}/export/final_message/{job_id}"
    return f"{export_url}/final_message/{job_id}"


def strip_markdown(text: str) -> str:
    text = re.sub(r"^[#>\-\*]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
    return text.strip()


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


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


def supports_spinner() -> bool:
    term = os.environ.get("TERM", "")
    return sys.stdout.isatty() and term.lower() != "dumb"


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


def fetch_json(url: str) -> dict[str, object]:
    req = Request(url=url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body) if body else {}
    return data if isinstance(data, dict) else {}


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


def print_final_export_summary(
    final_payload: dict[str, object],
    credentials_path: Path,
    *,
    show_password: bool = True,
    credentials: dict[str, object] | None = None,
) -> None:
    print_section("Final Export Summary", CYAN)
    print("Export complete.")

    raw_fields = parse_raw_api_message(str(final_payload.get("message") or ""))
    main_report = str(final_payload.get("main_report") or raw_fields.get("Report URL") or "").strip()
    username = str(final_payload.get("username") or raw_fields.get("Username") or "").strip()
    password = str(final_payload.get("password") or raw_fields.get("Password") or "").strip()
    if not password and isinstance(credentials, dict):
        password = str(credentials.get("password") or "").strip()

    if main_report:
        print("")
        print("Main Report")
        print_list_item("URL", main_report)

    if username or credentials_path.exists():
        print("")
        print("Access Credentials")
        if username:
            print_list_item("Username", username)
        if show_password and password:
            print_list_item("Password", password)
        print_list_item("Private file", str(credentials_path))

    publisher_results = final_payload.get("publisher_results")
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
            if url:
                print_list_item("URL", url)
            if publisher_username:
                print_list_item("Username", publisher_username)


def load_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def merge_credentials(current: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    merged = dict(current)
    raw_fields = parse_raw_api_message(str(payload.get("message") or ""))
    username = str(payload.get("username") or raw_fields.get("Username") or "").strip()
    password = str(payload.get("password") or raw_fields.get("Password") or "").strip()
    if username:
        merged["username"] = username
    if password:
        merged["password"] = password

    publishers: list[dict[str, str]] = []
    raw_publishers = payload.get("publisher_results")
    if isinstance(raw_publishers, list):
        for raw_publisher in raw_publishers:
            if not isinstance(raw_publisher, dict):
                continue
            publisher = {
                key: str(raw_publisher.get(key) or "").strip()
                for key in ("publisher", "url", "username", "password")
            }
            publishers.append({key: value for key, value in publisher.items() if value})
    if publishers:
        merged["publishers"] = publishers
    return merged


def collect_passwords(value: object) -> set[str]:
    secrets: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if "password" in str(key).lower() and isinstance(item, str) and item:
                secrets.add(item)
            else:
                secrets.update(collect_passwords(item))
    elif isinstance(value, list):
        for item in value:
            secrets.update(collect_passwords(item))
    return secrets


def redact_text(text: str, secrets: set[str]) -> str:
    redacted = text
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def redact_payload(value: object, secrets: set[str]) -> object:
    if isinstance(value, dict):
        return {
            key: redact_payload(item, secrets)
            for key, item in value.items()
            if "password" not in str(key).lower()
        }
    if isinstance(value, list):
        return [redact_payload(item, secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value


def read_saved_job_id(results_dir: Path) -> str:
    state_path = results_dir / "export_state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
        if isinstance(state, dict):
            job_id = str(state.get("job_id") or "").strip()
            if job_id:
                return job_id

    job_id_path = results_dir / "export_job_id.txt"
    if job_id_path.exists():
        return job_id_path.read_text(encoding="utf-8").strip()
    return ""


def build_refresh_payload(payload: dict[str, object]) -> dict[str, object]:
    allowed = {"project_name", "export_list", "backend", "authors", "expiry_days"}
    return {key: value for key, value in payload.items() if key in allowed}


def build_export_state(job_id: str, final_payload: dict[str, object], final_path: str) -> dict[str, object]:
    raw_message = str(final_payload.get("message") or "")
    raw_fields = parse_raw_api_message(raw_message)
    state: dict[str, object] = {
        "job_id": job_id,
        "final_path": final_path or None,
        "report_url": final_payload.get("main_report") or raw_fields.get("Report URL") or None,
        "download_url": raw_fields.get("Download URL") or None,
        "username": final_payload.get("username") or raw_fields.get("Username") or None,
    }
    return {key: value for key, value in state.items() if value not in {"", None}}


TERMINAL_STATUSES = {"completed", "completed_with_warning", "failed"}


def wait_for_final_message(
    export_url: str,
    job_id: str,
    *,
    poll_interval_seconds: int,
    timeout_seconds: int,
) -> tuple[dict[str, object], dict[str, object], str | None]:
    deadline = time.monotonic() + max(timeout_seconds, 1)
    last_error: str | None = None
    last_poll: dict[str, object] = {}
    poll_url = poll_endpoint(export_url, job_id)
    final_url = final_message_endpoint(export_url, job_id)
    while time.monotonic() < deadline:
        try:
            last_poll = fetch_json(poll_url)
            status = str(last_poll.get("status") or "").strip().lower()
            if status in TERMINAL_STATUSES:
                return fetch_json(final_url), last_poll, None
        except HTTPError as exc:
            last_error = f"{exc.code}: {exc.reason}"
            if exc.code not in {404, 425}:
                break
        except Exception as exc:
            last_error = str(exc)
        time.sleep(max(poll_interval_seconds, 1))
    return {}, last_poll, last_error or f"timed out after {timeout_seconds} seconds"


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    spec_path = results_dir / "export_job_spec.json"
    credentials_path = results_dir / "export_credentials.json"
    if not spec_path.exists():
        raise SystemExit(f"export spec not found: {spec_path}")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("export spec must be a JSON object")
    credentials = load_json_object(credentials_path)
    legacy_username = str(payload.pop("username", "") or "").strip()
    legacy_password = str(payload.pop("password", "") or "").strip()
    if legacy_username and not credentials.get("username"):
        credentials["username"] = legacy_username
    if legacy_password and not credentials.get("password"):
        credentials["password"] = legacy_password
    if legacy_username or legacy_password:
        spec_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if credentials:
        save_private_json(credentials_path, credentials)
    export_url = endpoint(args.api_url)
    refresh = parse_bool(args.refresh)
    show_password = parse_bool(args.show_password)
    job_id = args.job_id.strip() or (read_saved_job_id(results_dir) if refresh else "")
    submit_url = export_url
    submit_payload = payload
    action_label = "Submitting export job"

    if refresh:
        if not job_id:
            raise SystemExit("refresh requires --job-id or an existing export_job_id.txt/export_state.json")
        submit_url = refresh_endpoint(export_url, job_id)
        submit_payload = build_refresh_payload(payload)
        (results_dir / "export_refresh_spec.json").write_text(
            json.dumps(submit_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        action_label = "Refreshing export job"
    else:
        username = str(credentials.get("username") or "").strip()
        password = str(credentials.get("password") or "").strip()
        if not username or not password:
            raise SystemExit(
                f"create export requires complete credentials in {credentials_path}; rebuild the bundle first"
            )
        submit_payload = {**payload, "username": username, "password": password}

    req = Request(
        url=submit_url,
        data=json.dumps(submit_payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    body = run_with_spinner(
        action_label,
        lambda: urlopen(req, timeout=60).read().decode("utf-8", errors="replace"),
    )
    response = json.loads(body) if body else {}
    if not isinstance(response, dict):
        raise SystemExit("export engine returned a non-object response")
    response_job_id = str(response.get("job_id") or "").strip()
    if response_job_id:
        job_id = response_job_id
    if not job_id:
        raise SystemExit("export engine response did not include job_id")

    print_key_value("Job ID", job_id, tone=GREEN)
    print_key_value("Endpoint", submit_url)

    status_payload: dict[str, object] = {
        "job_id": job_id,
        "mode": "refresh" if refresh else "create",
        "submission": response,
    }
    raw_final_message = ""
    final_path = ""
    final_payload, poll_payload, final_error = run_with_spinner(
        "Waiting for final export status",
        lambda: wait_for_final_message(
            export_url,
            job_id,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
        ),
    )
    try:
        status_payload["poll"] = poll_payload
        status_payload["final_message"] = final_payload
        raw_final_message = str(final_payload.get("message") or "").strip()
        final_path = str(final_payload.get("final_path") or "").strip()
    except Exception:
        raw_final_message = ""
        final_path = ""
    if final_error:
        status_payload["final_message_error"] = final_error

    credentials = merge_credentials(credentials, response)
    credentials = merge_credentials(credentials, final_payload)
    if credentials:
        save_private_json(credentials_path, credentials)
    secrets = collect_passwords(credentials) | collect_passwords(response) | collect_passwords(final_payload)
    public_status = redact_payload(status_payload, secrets)
    public_final_payload = redact_payload(final_payload, secrets)
    if not isinstance(public_status, dict) or not isinstance(public_final_payload, dict):
        raise SystemExit("failed to sanitize export response")
    redacted_final_message = redact_text(raw_final_message, secrets)

    (results_dir / "export_submission.json").write_text(
        json.dumps(public_status, indent=2, sort_keys=True), encoding="utf-8"
    )
    (results_dir / "export_job_id.txt").write_text(job_id + "\n", encoding="utf-8")
    (results_dir / "export_final_message.txt").write_text(
        redacted_final_message + ("\n" if redacted_final_message else ""), encoding="utf-8"
    )
    (results_dir / "export_final_path.txt").write_text(final_path + ("\n" if final_path else ""), encoding="utf-8")
    (results_dir / "export_state.json").write_text(
        json.dumps(build_export_state(job_id, final_payload, final_path), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if final_error:
        print_section("Export Result", GREEN)
        print_key_value("Status", final_error, tone=YELLOW)
        if final_path:
            print_key_value("Final path", final_path)
        return 0

    if final_payload:
        print("")
        print_final_export_summary(
            final_payload if show_password else public_final_payload,
            credentials_path,
            show_password=show_password,
            credentials=credentials,
        )

    if raw_final_message:
        print("")
        print_section("JSON Patch for MS Planner", YELLOW)
        print(raw_final_message if show_password else redacted_final_message)
    elif final_path:
        print_section("Export Result", GREEN)
        print_key_value("Final path", final_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
