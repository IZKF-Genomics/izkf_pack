#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


CELLRANGER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
INPUT_COLUMNS = {"molecule_h5", "sample_outs", "vdj_contig_info"}
MODE_NAMES = {
    "molecule_h5": "Gene Expression / Feature Barcode molecule aggregation",
    "sample_outs": "complete cellranger multi aggregation",
    "vdj_contig_info": "V(D)J contig aggregation",
}
PLACEHOLDER_MARKERS = ("__EDIT_ME__", "EDIT_ME")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render or execute a Cell Ranger aggr workspace. The aggregation mode is inferred "
            "from the CSV header: molecule_h5, sample_outs, or vdj_contig_info."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    render = subparsers.add_parser("render", help="Stage the aggregation CSV and write editable settings.")
    render.add_argument("--aggregation-csv", required=True)
    render.add_argument("--cellranger-bin", default="cellranger")
    render.add_argument("--localcores", type=int, default=0)
    render.add_argument("--localmem", type=int, default=64)

    execute = subparsers.add_parser("execute", help="Validate inputs and run cellranger aggr.")
    execute.add_argument("--workspace", default=".")
    execute.add_argument("--results-dir", default="results")
    execute.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate inputs and write the exact runtime command without starting Cell Ranger.",
    )
    return parser.parse_args()


def info(message: str) -> None:
    print(f"[info] {message}")


def warning(message: str) -> None:
    print(f"[warning] {message}", file=sys.stderr)


def fail(message: str) -> None:
    raise SystemExit(f"[error] {message}")


def toml_string(value: object) -> str:
    return json.dumps(str(value))


def load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"settings file was not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def resolve_workspace_path(workspace: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (workspace / path).resolve()


def _contains_placeholder(value: str) -> bool:
    upper = value.upper()
    return any(marker in upper for marker in PLACEHOLDER_MARKERS)


def read_aggregation_csv(
    path: Path,
    *,
    workspace: Path,
    allow_placeholders: bool,
) -> tuple[str, list[str], list[dict[str, str]]]:
    if not path.is_file():
        fail(f"aggregation CSV was not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [str(field or "").strip() for field in (reader.fieldnames or [])]
        rows = [
            {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]

    if "sample_id" not in fieldnames:
        fail(f"{path} must contain a sample_id column")
    selected = [column for column in INPUT_COLUMNS if column in fieldnames]
    if len(selected) != 1:
        fail(
            f"{path} must contain exactly one input column: molecule_h5, sample_outs, "
            "or vdj_contig_info; found {', '.join(selected) if selected else 'none'}"
        )
    input_column = selected[0]
    required = {"sample_id", input_column}
    if input_column in {"sample_outs", "vdj_contig_info"}:
        required.update({"donor", "origin"})
    missing_columns = sorted(required.difference(fieldnames))
    if missing_columns:
        fail(f"{path} is missing required column(s): {', '.join(missing_columns)}")
    if len(rows) < 2:
        fail(f"{path} must contain at least two inputs; found {len(rows)}")

    seen_ids: set[str] = set()
    seen_paths: set[Path] = set()
    for number, row in enumerate(rows, start=2):
        sample_id = row.get("sample_id", "")
        if not sample_id:
            fail(f"empty sample_id in {path}:{number}")
        if sample_id in seen_ids:
            fail(f"duplicate sample_id {sample_id!r} in {path}:{number}")
        seen_ids.add(sample_id)

        raw_input = row.get(input_column, "")
        if not raw_input:
            fail(f"empty {input_column} in {path}:{number}")
        resolved = resolve_workspace_path(workspace, raw_input)
        if resolved in seen_paths:
            fail(f"the same input path is listed more than once: {resolved}")
        seen_paths.add(resolved)
        if input_column == "sample_outs":
            if not resolved.is_dir():
                fail(f"sample_outs directory does not exist: {resolved}")
        elif not resolved.is_file():
            fail(f"{input_column} file does not exist: {resolved}")
        row[input_column] = str(resolved)

        for column in required.difference({"sample_id", input_column}):
            value = row.get(column, "")
            if not value:
                fail(f"empty {column} in {path}:{number}")
            if _contains_placeholder(value) and not allow_placeholders:
                fail(
                    f"{column} still contains a placeholder in {path}:{number}. "
                    "Edit config/aggregation.csv and describe the real biological donor and origin."
                )

    return input_column, fieldnames, rows


def library_set(sample_outs: Path) -> tuple[str, ...]:
    libraries: set[str] = set()
    if (
        (sample_outs / "sample_molecule_info.h5").exists()
        or (sample_outs / "count").is_dir()
        or (sample_outs / "sample_filtered_feature_bc_matrix.h5").exists()
    ):
        libraries.add("count")
    for name in ("vdj_b", "vdj_t", "vdj_t_gd"):
        if (sample_outs / name).is_dir():
            libraries.add(name)
    return tuple(sorted(libraries))


def validate_mode_compatibility(mode: str, rows: list[dict[str, str]]) -> None:
    if mode == "sample_outs":
        combinations: dict[tuple[str, ...], list[str]] = {}
        for row in rows:
            combination = library_set(Path(row[mode]))
            combinations.setdefault(combination, []).append(row["sample_id"])
        if len(combinations) != 1:
            detail = "; ".join(
                f"{','.join(libraries) or 'unknown'}: {', '.join(samples)}"
                for libraries, samples in sorted(combinations.items())
            )
            fail(
                "full cellranger multi aggregation requires the same library combination in every "
                f"sample_outs directory. Found {detail}"
            )
    elif mode == "vdj_contig_info":
        known_chains = {
            Path(row[mode]).parent.name
            for row in rows
            if Path(row[mode]).parent.name in {"vdj_b", "vdj_t", "vdj_t_gd"}
        }
        if "vdj_t_gd" in known_chains:
            fail("Cell Ranger aggr does not support TRG/TRD-enriched V(D)J libraries")
        if len(known_chains) > 1:
            fail(f"V(D)J inputs have inconsistent chain types: {', '.join(sorted(known_chains))}")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_settings(
    path: Path,
    *,
    cellranger_bin: str,
    localcores: int,
    localmem: int,
) -> None:
    if localcores < 0 or localmem < 0:
        fail("localcores and localmem must not be negative")
    text = f'''[run]
# Cell Ranger creates results/<id>/ and resumes it if the directory already exists.
id = "aggregated"

[aggregation]
# "none" preserves all reads for downstream normalization/integration.
# "mapped" is the Cell Ranger default and downsamples libraries to comparable depth.
normalize = "none"

[analysis]
# Optional Cell Ranger aggr secondary-analysis controls.
nosecondary = false
enable_tsne = false
min_crispr_umi = 3

[runtime]
cellranger_bin = {toml_string(cellranger_bin)}
localcores = {max(0, localcores)}
localmem = {max(0, localmem)}
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_workspace(args: argparse.Namespace) -> int:
    workspace = Path.cwd().resolve()
    source = Path(args.aggregation_csv).expanduser().resolve()
    mode, fieldnames, rows = read_aggregation_csv(
        source,
        workspace=source.parent,
        allow_placeholders=True,
    )
    staged = workspace / "config" / "aggregation.csv"
    write_csv(staged, fieldnames, rows)
    write_settings(
        workspace / "config" / "cellranger_aggr.toml",
        cellranger_bin=args.cellranger_bin,
        localcores=args.localcores,
        localmem=args.localmem,
    )
    (workspace / "generated").mkdir(parents=True, exist_ok=True)
    (workspace / "results").mkdir(parents=True, exist_ok=True)

    info(f"detected mode: {MODE_NAMES[mode]}")
    info(f"staged {len(rows)} inputs in config/aggregation.csv")
    placeholders = sum(
        1 for row in rows for value in row.values() if _contains_placeholder(value)
    )
    if placeholders:
        warning(
            "the generated CSV contains donor/origin placeholders. Fill them with real biological "
            "metadata before execution; ./run.sh will refuse unresolved placeholders."
        )
    print("[next] review config/aggregation.csv and config/cellranger_aggr.toml")
    print("[next] run ./run.sh --prepare-only")
    print("[next] run ./run.sh after the preflight succeeds")
    return 0


def resolve_binary(value: str) -> str:
    candidate = str(os.getenv("CELLRANGER_BIN") or value).strip()
    if not candidate:
        fail("runtime.cellranger_bin must not be empty")
    if "/" in candidate:
        path = Path(candidate).expanduser().resolve()
        if not path.is_file():
            fail(f"Cell Ranger executable was not found: {path}")
        if not os.access(path, os.X_OK):
            fail(f"Cell Ranger file is not executable: {path}")
        return str(path)
    resolved = shutil.which(candidate)
    if not resolved:
        fail(
            f"Cell Ranger executable {candidate!r} was not found on PATH. Edit "
            "config/cellranger_aggr.toml or set CELLRANGER_BIN."
        )
    return resolved


def require_table(settings: dict[str, Any], name: str) -> dict[str, Any]:
    value = settings.get(name) or {}
    if not isinstance(value, dict):
        fail(f"[{name}] in config/cellranger_aggr.toml must be a TOML table")
    return value


def require_bool(table: dict[str, Any], key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        fail(f"analysis.{key} must be the TOML boolean true or false")
    return value


def build_command(
    settings: dict[str, Any],
    *,
    cellranger_bin: str,
    runtime_csv: Path,
) -> tuple[str, list[str]]:
    run = require_table(settings, "run")
    aggregation = require_table(settings, "aggregation")
    analysis = require_table(settings, "analysis")
    runtime = require_table(settings, "runtime")

    run_id = str(run.get("id") or "").strip()
    if not CELLRANGER_ID_RE.fullmatch(run_id):
        fail("run.id must contain only letters, numbers, underscores, or hyphens and be at most 64 characters")
    normalize = str(aggregation.get("normalize") or "").strip().lower()
    if normalize not in {"none", "mapped"}:
        fail("aggregation.normalize must be either 'none' or 'mapped'")
    localcores = int(runtime.get("localcores") or 0)
    localmem = int(runtime.get("localmem") or 0)
    if localcores < 0 or localmem < 0:
        fail("runtime.localcores and runtime.localmem must not be negative")
    if localmem and localmem < 64:
        warning(
            f"localmem={localmem} GB is below the 64 GB minimum recommended by 10x Genomics "
            "for aggregations up to 250,000 cells"
        )

    min_crispr_umi = int(analysis.get("min_crispr_umi", 3))
    if min_crispr_umi < 1:
        fail("analysis.min_crispr_umi must be at least 1")
    nosecondary = require_bool(analysis, "nosecondary", False)
    enable_tsne = require_bool(analysis, "enable_tsne", False)

    command = [
        cellranger_bin,
        "aggr",
        f"--id={run_id}",
        f"--csv={runtime_csv}",
        f"--normalize={normalize}",
        f"--min-crispr-umi={min_crispr_umi}",
        f"--enable-tsne={'true' if enable_tsne else 'false'}",
    ]
    if nosecondary:
        command.append("--nosecondary")
    if localcores > 0:
        command.append(f"--localcores={localcores}")
    if localmem > 0:
        command.append(f"--localmem={localmem}")
    return run_id, command


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cellranger_version(binary: str) -> str:
    completed = subprocess.run(
        [binary, "--version"], text=True, capture_output=True, check=False
    )
    output = (completed.stdout or completed.stderr).strip()
    return output or f"version command exited {completed.returncode}"


def execute_workspace(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    results_dir = resolve_workspace_path(workspace, args.results_dir)
    settings_path = workspace / "config" / "cellranger_aggr.toml"
    source_csv = workspace / "config" / "aggregation.csv"
    runtime_csv = workspace / "generated" / "aggregation.csv"
    settings = load_toml(settings_path)
    mode, fieldnames, rows = read_aggregation_csv(
        source_csv,
        workspace=workspace,
        allow_placeholders=False,
    )
    validate_mode_compatibility(mode, rows)
    write_csv(runtime_csv, fieldnames, rows)

    runtime = require_table(settings, "runtime")
    cellranger_bin = resolve_binary(str(runtime.get("cellranger_bin") or "cellranger"))
    run_id, command = build_command(
        settings,
        cellranger_bin=cellranger_bin,
        runtime_csv=runtime_csv,
    )
    results_dir.mkdir(parents=True, exist_ok=True)
    version = cellranger_version(cellranger_bin)
    write_json(
        results_dir / "runtime_command.json",
        {
            "command": command,
            "command_shell": shlex.join(command),
            "input_count": len(rows),
            "input_mode": mode,
            "input_mode_description": MODE_NAMES[mode],
            "normalization": str(require_table(settings, "aggregation").get("normalize")),
            "run_id": run_id,
            "working_directory": str(results_dir),
        },
    )
    write_json(
        results_dir / "software_versions.json",
        {
            "cellranger": {"command": [cellranger_bin, "--version"], "version": version},
            "python": {"version": sys.version.split()[0]},
        },
    )

    info(f"mode: {MODE_NAMES[mode]}")
    info(f"validated {len(rows)} inputs from config/aggregation.csv")
    info(f"normalization: {require_table(settings, 'aggregation').get('normalize')}")
    info(f"Cell Ranger: {version}")
    print(f"[command] {shlex.join(command)}")
    if args.prepare_only:
        print("[ready] preflight succeeded; Cell Ranger was not started")
        print("[next] run ./run.sh")
        return 0

    info(f"running in {results_dir}")
    completed = subprocess.run(command, cwd=results_dir, check=False)
    if completed.returncode != 0:
        fail(
            f"Cell Ranger exited with status {completed.returncode}. Review its error log under "
            f"{results_dir / run_id} and rerun ./run.sh to resume after correcting the problem."
        )
    output_dir = results_dir / run_id / "outs"
    if not output_dir.is_dir():
        fail(f"Cell Ranger reported success but the expected output directory is missing: {output_dir}")
    print(f"[done] Cell Ranger aggr completed: {output_dir}")
    print("[next] review web_summary.html before downstream analysis")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "render":
        return render_workspace(args)
    return execute_workspace(args)


if __name__ == "__main__":
    raise SystemExit(main())
