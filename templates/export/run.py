#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or update a project export. The first run creates an export; "
            "later runs automatically update the saved export while preserving its "
            "job ID, username, password, and publisher links."
        ),
        epilog=(
            "Typical use:\n"
            "  linkar run export\n"
            "  linkar run export --refresh\n"
            "  linkar run export --refresh --prepare\n\n"
            "Existing specifications are preserved unless Linkar runs with --refresh."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--results-dir", default="./results", help="Directory for generated export artifacts.")
    parser.add_argument("--project-dir", default="..", help="Linkar project directory containing project.yaml.")
    parser.add_argument("--template-dir", default=".", help="Export template directory containing helper scripts.")
    parser.add_argument("--prepare", action="store_true", help="Prepare the export without contacting the export service.")
    parser.add_argument(
        "--new",
        action="store_true",
        help=(
            "Create a new export identity and credentials. This also rebuilds the specification "
            "and is refused while the saved export is active."
        ),
    )
    parser.add_argument(
        "--job-id",
        default="",
        help="Update this existing job; normally the job ID is read from results/export_state.json.",
    )
    parser.add_argument("--hide-password", action="store_true", help="Do not print passwords in terminal output.")
    parser.add_argument("--export-engine-api-url", required=True, help="Base URL of the export engine; /export is appended if needed.")
    parser.add_argument("--export-engine-backends", default="apache, owncloud, sftp", help="Comma-separated export backends.")
    parser.add_argument("--export-expiry-days", type=int, default=30, help="Retention period recorded in the export spec.")
    parser.add_argument("--export-username", default="", help="Optional username override; derived from project name if omitted.")
    parser.add_argument("--agendo-id", default="", help="Optional Agendo request id for metadata lookup.")
    parser.add_argument("--flowcell-id", default="", help="Optional flowcell id for metadata lookup.")
    parser.add_argument("--metadata-source", default="auto", help="Metadata source mode: auto, api, file, mock, or none.")
    parser.add_argument("--metadata-file", default="", help="Optional JSON/YAML metadata file, resolved relative to the project.")
    parser.add_argument("--metadata-api-url", default="https://genomics.rwth-aachen.de/api", help="Base URL for metadata enrichment.")
    parser.add_argument("--metadata-api-endpoint", default="/project-output", help="Metadata API endpoint path.")
    parser.add_argument("--metadata-api-timeout", type=int, default=20, help="Metadata API timeout in seconds.")
    parser.add_argument("--include-summary-in-spec", default="true", help="Include generated project summary context in the export spec.")
    parser.add_argument("--summary-style", default="full", help="Summary report style: full or concise.")
    parser.add_argument("--poll-interval-seconds", type=int, default=2, help="Poll interval for GET /export/{job_id}/poll.")
    parser.add_argument("--timeout-seconds", type=int, default=3600, help="Timeout while polling for final export status.")
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


def run_python_script(script_path: Path, args: list[str]) -> None:
    completed = subprocess.run(
        [sys.executable, str(script_path), *args],
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_saved_job_id(results_dir: Path) -> str:
    state = load_json(results_dir / "export_state.json")
    job_id = str(state.get("job_id") or "").strip()
    if job_id:
        return job_id
    job_id_path = results_dir / "export_job_id.txt"
    if job_id_path.exists():
        return job_id_path.read_text(encoding="utf-8").strip()
    return ""


def export_endpoint(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    return base if base.endswith("/export") else f"{base}/export"


def ensure_new_export_is_safe(api_url: str, job_id: str) -> None:
    """Refuse to replace local credentials while the saved export is active."""
    request = Request(
        url=f"{export_endpoint(api_url)}/{job_id}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if exc.code == 404:
            return
        raise SystemExit(f"Could not verify saved export {job_id}: HTTP {exc.code}") from exc
    except (OSError, URLError) as exc:
        raise SystemExit(f"Could not verify saved export {job_id}: {exc}") from exc

    try:
        record = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not verify saved export {job_id}: invalid API response") from exc
    if not isinstance(record, dict):
        raise SystemExit(f"Could not verify saved export {job_id}: invalid API response")
    if str(record.get("record_status") or "").strip().lower() == "active":
        raise SystemExit(
            f"Cannot use --new while saved export {job_id} is active. "
            "Use the normal command to update it, or clean the active export first."
        )


def load_project_template_counts(project_path: Path) -> list[tuple[str, int]]:
    project_yaml = project_path / "project.yaml"
    if not project_yaml.exists():
        return []
    payload = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    templates = payload.get("templates") or []
    counts: OrderedDict[str, int] = OrderedDict()
    for entry in templates:
        if not isinstance(entry, dict):
            continue
        template_id = str(entry.get("id") or "").strip()
        if template_id and template_id != "export":
            counts[template_id] = counts.get(template_id, 0) + 1
    return list(counts.items())


def describe_prepared_bundle(project_dir: Path, results_dir: Path) -> None:
    spec = load_json(results_dir / "export_job_spec.json")
    template_counts = load_project_template_counts(project_dir)
    export_list = spec.get("export_list") or []
    authors = spec.get("authors") or []
    backends = spec.get("backend") or []

    print_key_value("Project", str(spec.get("project_name") or project_dir.name))
    if template_counts:
        summary = ", ".join(f"{template_id} ({count})" for template_id, count in template_counts)
        print_key_value("Project templates", summary)
    print_key_value("Export entries", str(len(export_list)))
    if isinstance(backends, list) and backends:
        print_key_value("Backends", ", ".join(str(item) for item in backends))
    if isinstance(authors, list) and authors:
        print_key_value("Authors", ", ".join(str(item) for item in authors))
    print_key_value("Spec", str((results_dir / "export_job_spec.json").resolve()))


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    project_dir = Path(args.project_dir).resolve()
    template_dir = Path(args.template_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    if not (project_dir / "project.yaml").exists():
        raise SystemExit(f"project.yaml not found in {project_dir}")

    spec_path = results_dir / "export_job_spec.json"
    build_script = template_dir / "build_export_bundle.py"
    submit_script = template_dir / "submit_export.py"
    linkar_refresh = parse_bool(os.environ.get("LINKAR_REFRESH", "false"))
    existing_job_id = args.job_id.strip() or read_saved_job_id(results_dir)
    if args.job_id.strip() and args.new:
        raise SystemExit("--job-id and --new cannot be used together")
    if args.prepare and args.new:
        raise SystemExit("--prepare and --new cannot be used together")
    if args.new and existing_job_id:
        ensure_new_export_is_safe(args.export_engine_api_url, existing_job_id)
    update_existing = not args.new and bool(existing_job_id)
    rebuild_spec = args.new or linkar_refresh or not spec_path.exists()

    print_section("Prepare Export Bundle")
    if not rebuild_spec:
        print(color("[info]", YELLOW, bold=True), f"using existing {spec_path}")
    else:
        if spec_path.exists():
            print(color("[info]", YELLOW, bold=True), f"rebuilding existing {spec_path}")
        run_python_script(
            build_script,
            [
                "--project-dir",
                str(project_dir),
                "--template-dir",
                str(template_dir),
                "--results-dir",
                str(results_dir),
                "--export-engine-backends",
                args.export_engine_backends,
                "--export-expiry-days",
                str(args.export_expiry_days),
                "--export-username",
                args.export_username,
                *(["--new"] if args.new else []),
                "--agendo-id",
                args.agendo_id,
                "--flowcell-id",
                args.flowcell_id,
                "--metadata-source",
                args.metadata_source,
                "--metadata-file",
                args.metadata_file,
                "--metadata-api-url",
                args.metadata_api_url,
                "--metadata-api-endpoint",
                args.metadata_api_endpoint,
                "--metadata-api-timeout",
                str(args.metadata_api_timeout),
                "--include-summary-in-spec",
                str(args.include_summary_in_spec),
                "--summary-style",
                args.summary_style,
            ],
        )

    describe_prepared_bundle(project_dir, results_dir)

    if args.prepare:
        print_section("Prepare Complete", GREEN)
        print("Prepared the export bundle without contacting the export API.")
        return 0

    print_section("Update Export" if update_existing else "Create Export", GREEN)
    submit_args = [
        "--results-dir",
        str(results_dir),
        "--api-url",
        args.export_engine_api_url,
        "--mode",
        "update" if update_existing else "create",
        "--poll-interval-seconds",
        str(args.poll_interval_seconds),
        "--timeout-seconds",
        str(args.timeout_seconds),
        *(["--hide-password"] if args.hide_password else []),
    ]
    if update_existing:
        submit_args.extend(["--job-id", existing_job_id])
    run_python_script(
        submit_script,
        submit_args,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
