#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete an export project from the facility export engine.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--export-engine-api-url", default="http://genomics.rwth-aachen.de:9500/export")
    parser.add_argument("--confirm-delete", default="false")
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


def normalize_delete_endpoint(base_url: str, project_id: str) -> str:
    api_clean = base_url.rstrip("/")
    root = api_clean if api_clean.endswith("/export") else f"{api_clean}/export"
    return f"{root}/{project_id}"


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
    project_id = args.project_id.strip()
    if not project_id:
        raise SystemExit("project_id must be provided.")
    if not parse_bool(args.confirm_delete, False):
        raise SystemExit("Deletion is destructive. Re-run with --confirm-delete true.")

    endpoint = normalize_delete_endpoint(args.export_engine_api_url, project_id)
    req = Request(endpoint, headers={"Accept": "application/json"}, method="DELETE")

    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise SystemExit(f"Delete API request failed: {exc.code} {detail}")
    except URLError as exc:
        raise SystemExit(f"Delete API request failed: {exc.reason}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise SystemExit("Delete API returned a non-JSON response")

    if not isinstance(parsed, dict):
        raise SystemExit("Delete API returned a non-object response")

    write_json(results_dir / "delete_response.json", parsed)
    write_text(results_dir / "export_project_id.txt", project_id + "\n")

    print_section("Export Deletion Request", BLUE)
    print_key_value("Endpoint", endpoint)
    print_key_value("Project", project_id)

    print_section("Deletion Result", GREEN)
    status = parsed.get("status") or parsed.get("message") or "completed"
    print_key_value("Status", str(status), tone=GREEN)
    print(json.dumps(parsed, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
