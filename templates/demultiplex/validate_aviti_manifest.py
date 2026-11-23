#!/usr/bin/env python3
"""Validate an AVITI RunManifest against the run's index cycle counts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def index_cycles(run_dir: Path) -> tuple[int, int]:
    parameters_path = run_dir / "RunParameters.json"
    try:
        parameters = json.loads(parameters_path.read_text(encoding="utf-8"))
        cycles = parameters["Cycles"]
        return int(cycles["I1"]), int(cycles["I2"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"cannot read I1/I2 cycle counts from {parameters_path}: {exc}"
        ) from exc


def sample_rows(manifest_path: Path) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    try:
        rows = list(csv.reader(manifest_path.open(newline="", encoding="utf-8-sig")))
    except OSError as exc:
        raise ValueError(f"cannot read RunManifest {manifest_path}: {exc}") from exc

    section_index = next(
        (index for index, row in enumerate(rows) if row and row[0].strip().upper() == "[SAMPLES]"),
        None,
    )
    if section_index is None or section_index + 1 >= len(rows):
        raise ValueError(f"{manifest_path} has no [SAMPLES] section with a header")

    header = [column.strip() for column in rows[section_index + 1]]
    required = ("SampleName", "Index1", "Index2", "Lane")
    missing = [column for column in required if column not in header]
    if missing:
        raise ValueError(f"{manifest_path} [SAMPLES] header is missing: {', '.join(missing)}")

    parsed: list[tuple[int, dict[str, str]]] = []
    for line_number, row in enumerate(rows[section_index + 2 :], start=section_index + 3):
        if not row or not any(value.strip() for value in row):
            continue
        if row[0].strip().startswith("["):
            break
        padded = row + [""] * max(0, len(header) - len(row))
        parsed.append((line_number, dict(zip(header, (value.strip() for value in padded)))))
    return header, parsed


def validate(run_dir: Path, manifest_path: Path) -> list[str]:
    i1_cycles, i2_cycles = index_cycles(run_dir)
    _, rows = sample_rows(manifest_path)
    errors: list[str] = []
    if not rows:
        return [f"{manifest_path}: [SAMPLES] contains no sample rows"]

    for line_number, row in rows:
        sample = row.get("SampleName") or "<empty>"
        for column, expected in (("Index1", i1_cycles), ("Index2", i2_cycles)):
            sequence = row.get(column, "")
            if len(sequence) != expected:
                errors.append(
                    f"{manifest_path}:{line_number}: {sample} {column} has {len(sequence)} bases; "
                    f"RunParameters.json requires {expected}"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    try:
        errors = validate(args.run_dir, args.manifest)
    except ValueError as exc:
        print(f"AVITI RunManifest validation failed: {exc}", file=sys.stderr)
        return 2

    if errors:
        print("AVITI RunManifest validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    i1_cycles, i2_cycles = index_cycles(args.run_dir)
    print(f"AVITI RunManifest validated (Index1={i1_cycles} bp, Index2={i2_cycles} bp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
