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
    parser = argparse.ArgumentParser(description="Query the facility export engine for a job status.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--export-engine-api-url", default="http://genomics.rwth-aachen.de:9500/export")
    return parser.parse_args()


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def ansi(code: str) -> str:
    return f"\033[{code}m" if supports_color() else ""


RESET = ansi("0")
BOLD = ansi("1")
BLUE = ansi("34")
CYAN = ansi("36")
GREEN = ansi("32")


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


def normalize_status_endpoint(base_url: str, job_id: str) -> str:
    api_clean = base_url.rstrip("/")
    root = api_clean if api_clean.endswith("/export") else f"{api_clean}/export"
    return f"{root}/status/{job_id}"


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
    job_id = args.job_id.strip()
    if not job_id:
        raise SystemExit("job_id must be provided.")

    endpoint = normalize_status_endpoint(args.export_engine_api_url, job_id)
    req = Request(endpoint, headers={"Accept": "application/json"}, method="GET")

    try:
        with urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise SystemExit(f"Status API request failed: {exc.code} {detail}")
    except URLError as exc:
        raise SystemExit(f"Status API request failed: {exc.reason}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise SystemExit("Status API returned a non-JSON response")

    if not isinstance(parsed, dict):
        raise SystemExit("Status API returned a non-object response")

    write_json(results_dir / "export_status.json", parsed)
    write_text(results_dir / "export_job_id.txt", job_id + "\n")

    print_section("Export Status Request", BLUE)
    print_key_value("Endpoint", endpoint)
    print_key_value("job_id", job_id)

    print_section("Export Status", GREEN)
    status = parsed.get("status") or parsed.get("type") or "unknown"
    print_key_value("Status", str(status), tone=GREEN)
    if parsed.get("job_id"):
        print_key_value("job_id", str(parsed["job_id"]), tone=GREEN)
    if parsed.get("main_report"):
        print_key_value("Report URL", str(parsed["main_report"]), tone=GREEN)
    print(json.dumps(parsed, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
