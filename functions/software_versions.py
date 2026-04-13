from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


TOOL_COMMANDS: dict[str, list[str]] = {
    "R": ["pixi", "run", "Rscript", "--version"],
    "bcl-convert": ["bcl-convert", "--version"],
    "nextflow": ["nextflow", "-version"],
    "pixi": ["pixi", "--version"],
    "python": [sys.executable, "--version"],
    "quarto": ["quarto", "--version"],
}


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


def normalize_named_entries(entries: Any) -> list[dict[str, Any]]:
    if entries is None:
        return []
    if isinstance(entries, dict):
        normalized = []
        for name, value in entries.items():
            if isinstance(value, dict):
                entry = {"name": str(name), **value}
            else:
                entry = {"name": str(name), "version": value}
            normalized.append(entry)
        return normalized
    if isinstance(entries, list):
        normalized = []
        for item in entries:
            if isinstance(item, str):
                normalized.append({"name": item})
            elif isinstance(item, dict):
                normalized.append(dict(item))
            else:
                raise ValueError(f"Unsupported spec entry type: {type(item).__name__}")
        return normalized
    raise ValueError(f"Unsupported spec entries container: {type(entries).__name__}")


def resolve_env_fields(entry: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key, value in entry.items():
        if key.endswith("_env") and isinstance(value, str):
            resolved[key.removesuffix("_env")] = os.environ.get(value, "")
        else:
            resolved[key] = value
    return resolved


def commands_from_tool_specs(entries: Any) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {}
    for entry in normalize_named_entries(entries):
        tool_id = str(entry.get("tool") or entry.get("id") or entry.get("name") or "").strip()
        if not tool_id:
            raise ValueError("Tool spec entries must define a name, id, or tool field.")
        command = TOOL_COMMANDS.get(tool_id)
        if command is None:
            supported = ", ".join(sorted(TOOL_COMMANDS))
            raise ValueError(f"Unknown tool id '{tool_id}'. Supported tool ids: {supported}")
        output_name = str(entry.get("name") or tool_id).strip()
        commands[output_name] = list(command)
    return commands


def static_from_specs(entries: Any, *, source: str) -> dict[str, dict[str, Any]]:
    static: dict[str, dict[str, Any]] = {}
    for raw_entry in normalize_named_entries(entries):
        entry = resolve_env_fields(raw_entry)
        name = str(entry.pop("name", "")).strip()
        if not name:
            raise ValueError("Static and param spec entries must define a name field.")
        env_name = entry.pop("env", None)
        if env_name is not None and "version" not in entry:
            entry["version"] = os.environ.get(str(env_name), "")
        entry.setdefault("source", source)
        if "version" not in entry:
            raise ValueError(f"Spec entry '{name}' must define version or version_env.")
        static[name] = entry
    return static


def load_spec(path: str | Path) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("software versions spec must be a mapping at the top level")

    commands: dict[str, list[str]] = {}
    commands.update(commands_from_tool_specs(raw.get("tools")))

    static: dict[str, dict[str, Any]] = {}
    static.update(static_from_specs(raw.get("static"), source="static"))
    static.update(static_from_specs(raw.get("params"), source="param"))
    return commands, static


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
    spec_path: str | Path | None = None,
    commands: dict[str, list[str]] | None = None,
    static: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_commands: dict[str, list[str]] = {}
    merged_static: dict[str, Any] = {}
    if spec_path is not None:
        spec_commands, spec_static = load_spec(spec_path)
        merged_commands.update(spec_commands)
        merged_static.update(spec_static)
    merged_commands.update(commands or {})
    merged_static.update(static or {})
    payload = collect_software_versions(commands=merged_commands, static=merged_static)
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
    parser.add_argument("--spec", help="Path to a template-level software_versions_spec.yaml file.")
    parser.add_argument("--command", action="append", default=[], help="NAME=COMMAND")
    parser.add_argument("--static", action="append", default=[], help="NAME=VALUE")
    args = parser.parse_args()

    commands = dict(parse_command(item) for item in args.command)
    static = dict(parse_static(item) for item in args.static)
    write_software_versions(args.output, spec_path=args.spec, commands=commands, static=static)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
