#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and optionally submit an export bundle.")
    parser.add_argument("--results-dir", default="./results")
    parser.add_argument("--project-dir", default="..")
    parser.add_argument("--template-dir", default=".")
    parser.add_argument("--dry-run", default="false")
    parser.add_argument("--reuse-spec", default="false")
    parser.add_argument("--reuse-credentials", default="false")
    parser.add_argument("--export-engine-api-url", required=True)
    parser.add_argument("--export-engine-backends", default="apache, owncloud, sftp")
    parser.add_argument("--export-expiry-days", type=int, default=30)
    parser.add_argument("--export-username", default="")
    parser.add_argument("--export-password", default="")
    parser.add_argument("--agendo-id", default="")
    parser.add_argument("--flowcell-id", default="")
    parser.add_argument("--metadata-source", default="auto")
    parser.add_argument("--metadata-file", default="")
    parser.add_argument("--metadata-api-url", default="")
    parser.add_argument("--metadata-api-endpoint", default="/project-output")
    parser.add_argument("--metadata-api-timeout", type=int, default=20)
    parser.add_argument("--include-methods-in-spec", default="true")
    parser.add_argument("--methods-style", default="full")
    parser.add_argument("--poll-interval-seconds", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
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
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


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
    reuse_spec = parse_bool(args.reuse_spec)
    reuse_credentials = parse_bool(args.reuse_credentials)

    print_section("Prepare Export Bundle")
    if reuse_spec:
        if not spec_path.exists():
            raise SystemExit(f"cannot reuse missing export spec: {spec_path}")
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
                "--export-password",
                args.export_password,
                "--reuse-saved-credentials",
                "true" if reuse_credentials else "false",
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
                "--include-methods-in-spec",
                str(args.include_methods_in_spec),
                "--methods-style",
                args.methods_style,
            ],
        )

    describe_prepared_bundle(project_dir, results_dir)

    if parse_bool(args.dry_run):
        print_section("Dry Run Complete", GREEN)
        print("Prepared the export bundle without contacting the export API.")
        return 0

    print_section("Submit Export", GREEN)
    run_python_script(
        submit_script,
        [
            "--results-dir",
            str(results_dir),
            "--api-url",
            args.export_engine_api_url,
            "--poll-interval-seconds",
            str(args.poll_interval_seconds),
            "--timeout-seconds",
            str(args.timeout_seconds),
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
