#!/usr/bin/env python3
"""Validate an AVITI RunManifest against the run's index cycle counts."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path


INDEX_RE = re.compile(r"^[ACGTN]+$")
LANE_RE = re.compile(r"^[1-9][0-9]*(?:\+[1-9][0-9]*)*$")


def run_configuration(run_dir: Path) -> tuple[int, int, set[int]]:
    parameters_path = run_dir / "RunParameters.json"
    try:
        parameters = json.loads(parameters_path.read_text(encoding="utf-8"))
        cycles = parameters["Cycles"]
        analysis_lanes = str(parameters["AnalysisLanes"])
        if not LANE_RE.fullmatch(analysis_lanes):
            raise ValueError(f"invalid AnalysisLanes value {analysis_lanes!r}")
        lanes = {int(lane) for lane in analysis_lanes.split("+")}
        return int(cycles["I1"]), int(cycles["I2"]), lanes
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"cannot read I1/I2 cycle counts and AnalysisLanes from {parameters_path}: {exc}"
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
    i1_cycles, i2_cycles, run_lanes = run_configuration(run_dir)
    _, rows = sample_rows(manifest_path)
    errors: list[str] = []
    if not rows:
        return [f"{manifest_path}: [SAMPLES] contains no sample rows"]

    seen_index_pairs: list[tuple[int, str, str, frozenset[int], str]] = []
    for line_number, row in rows:
        sample_name = row.get("SampleName", "")
        sample = sample_name or "<empty>"
        if not sample_name:
            errors.append(f"{manifest_path}:{line_number}: SampleName is empty")

        for column, expected in (("Index1", i1_cycles), ("Index2", i2_cycles)):
            sequence = row.get(column, "")
            if len(sequence) != expected:
                errors.append(
                    f"{manifest_path}:{line_number}: {sample} {column} has {len(sequence)} bases; "
                    f"RunParameters.json requires {expected}"
                )
            invalid = sorted(set(sequence) - set("ACGTN"))
            if not INDEX_RE.fullmatch(sequence):
                detail = ", ".join(repr(character) for character in invalid) or "empty value"
                errors.append(
                    f"{manifest_path}:{line_number}: {sample} {column} contains invalid "
                    f"base characters: {detail}; allowed characters are A, C, G, T, N"
                )

        lane_value = row.get("Lane", "")
        lanes: frozenset[int] = frozenset()
        if not LANE_RE.fullmatch(lane_value):
            errors.append(
                f"{manifest_path}:{line_number}: {sample} Lane {lane_value!r} is invalid; "
                "use positive lane numbers joined by '+' (for example, 1 or 1+2)"
            )
        else:
            lanes = frozenset(int(lane) for lane in lane_value.split("+"))
            unknown_lanes = lanes - run_lanes
            if unknown_lanes:
                errors.append(
                    f"{manifest_path}:{line_number}: {sample} uses lane(s) "
                    f"{','.join(map(str, sorted(unknown_lanes)))}; RunParameters.json allows "
                    f"{'+'.join(map(str, sorted(run_lanes)))}"
                )

        project = row.get("Project", "")
        if project and (
            project in {".", ".."}
            or "/" in project
            or "\\" in project
            or any(ord(character) < 32 for character in project)
        ):
            errors.append(
                f"{manifest_path}:{line_number}: {sample} Project {project!r} is unsafe as a "
                "single output-directory name"
            )

        index1 = row.get("Index1", "")
        index2 = row.get("Index2", "")
        if lanes and not (lanes - run_lanes):
            for previous_line, previous_sample, previous_i1, previous_lanes, previous_i2 in seen_index_pairs:
                overlap = lanes & previous_lanes
                if index1 == previous_i1 and index2 == previous_i2 and overlap:
                    errors.append(
                        f"{manifest_path}:{line_number}: {sample} duplicates the Index1/Index2 "
                        f"pair from line {previous_line} ({previous_sample}) on overlapping "
                        f"lane(s) {','.join(map(str, sorted(overlap)))}"
                    )
            seen_index_pairs.append((line_number, sample, index1, lanes, index2))
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

    i1_cycles, i2_cycles, run_lanes = run_configuration(args.run_dir)
    print(
        f"AVITI RunManifest validated (Index1={i1_cycles} bp, Index2={i2_cycles} bp, "
        f"lanes={'+'.join(map(str, sorted(run_lanes)))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
