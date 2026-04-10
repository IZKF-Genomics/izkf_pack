from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


def run_version_command(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        return {
            "command": " ".join(shlex.quote(part) for part in command),
            "source": "command",
            "error": str(exc),
        }
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    return {
        "version": output.splitlines()[0] if output else "",
        "raw": output,
        "command": " ".join(shlex.quote(part) for part in command),
        "source": "command",
        "returncode": completed.returncode,
    }


def normalize_static_entry(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        out = dict(value)
    else:
        out = {"version": str(value)}
    out.setdefault("source", "static")
    return out


def collect_software_versions(
    *,
    commands: dict[str, list[str]] | None = None,
    static: dict[str, Any] | None = None,
) -> dict[str, Any]:
    software: list[dict[str, Any]] = []
    for name, command in (commands or {}).items():
        entry = {"name": name}
        entry.update(run_version_command(command))
        software.append(entry)
    for name, value in (static or {}).items():
        entry = {"name": name}
        entry.update(normalize_static_entry(value))
        software.append(entry)
    return {"software": software}


def write_software_versions(
    output_path: str | Path,
    *,
    commands: dict[str, list[str]] | None = None,
    static: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = collect_software_versions(commands=commands, static=static)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def parse_command(value: str) -> tuple[str, list[str]]:
    if "=" not in value:
        raise ValueError("--command must use NAME=COMMAND")
    name, command = value.split("=", 1)
    return name.strip(), shlex.split(command.strip())


def parse_static(value: str) -> tuple[str, dict[str, Any]]:
    if "=" not in value:
        raise ValueError("--static must use NAME=VALUE")
    name, raw = value.split("=", 1)
    return name.strip(), {"version": raw.strip(), "source": "static"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a software_versions.json file.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--command", action="append", default=[], help="NAME=COMMAND")
    parser.add_argument("--static", action="append", default=[], help="NAME=VALUE")
    args = parser.parse_args()

    commands = dict(parse_command(item) for item in args.command)
    static = dict(parse_static(item) for item in args.static)
    write_software_versions(args.output, commands=commands, static=static)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
