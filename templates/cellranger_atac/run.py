#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path


FASTQ_PATTERN = re.compile(
    r"^(?P<sample>.+?)_S\d+(?:_L\d{3})?_[RI]\d(?:_\d{3})?\.f(?:ast)?q\.gz$"
)
CELLRANGER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run cellranger-atac count for each sample discovered in a FASTQ directory."
    )
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--fastq-dir", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--cellranger-atac-bin", default="cellranger-atac")
    parser.add_argument("--run-aggr", default="true")
    parser.add_argument("--localcores", type=int, default=0)
    parser.add_argument("--localmem", type=int, default=0)
    return parser.parse_args()


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise SystemExit(f"Invalid boolean value: {value}")


def discover_samples(fastq_dir: Path) -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    for pattern in ("*.fastq.gz", "*.fq.gz"):
        for fastq_path in sorted(fastq_dir.glob(pattern)):
            match = FASTQ_PATTERN.match(fastq_path.name)
            if not match:
                continue
            sample = match.group("sample")
            discovered.setdefault(sample, []).append(fastq_path.name)
    return discovered


def validate_sample_ids(samples: dict[str, list[str]]) -> None:
    invalid = [sample for sample in sorted(samples) if not CELLRANGER_ID_PATTERN.fullmatch(sample)]
    if invalid:
        joined = ", ".join(invalid)
        raise SystemExit(
            "Discovered sample names are not valid Cell Ranger ids "
            f"(allowed: [A-Za-z0-9_-], max length 64): {joined}"
        )


def build_common_flags(args: argparse.Namespace) -> list[str]:
    common: list[str] = []
    if args.localcores > 0:
        common.extend(["--localcores", str(args.localcores)])
    if args.localmem > 0:
        common.extend(["--localmem", str(args.localmem)])
    return common


def run_command(command: list[str], cwd: Path) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_aggregation_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["library_id", "fragments", "cells"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    run_aggr = parse_bool(args.run_aggr)
    results_dir = Path(args.results_dir).resolve()
    fastq_dir = Path(args.fastq_dir).resolve()
    reference = Path(args.reference).resolve()
    counts_dir = results_dir / "counts"
    combined_dir = results_dir / "combined"
    aggregation_csv = results_dir / "aggregation.csv"

    if not fastq_dir.is_dir():
        raise SystemExit(f"FASTQ directory not found: {fastq_dir}")
    if not reference.exists():
        raise SystemExit(f"Reference path not found: {reference}")

    results_dir.mkdir(parents=True, exist_ok=True)
    counts_dir.mkdir(parents=True, exist_ok=True)

    samples = discover_samples(fastq_dir)
    if not samples:
        raise SystemExit(
            "No FASTQ files matching the Cell Ranger naming pattern were found in "
            f"{fastq_dir}"
        )
    validate_sample_ids(samples)

    manifest = []
    common_flags = build_common_flags(args)
    aggregation_rows: list[dict[str, str]] = []

    for sample, files in sorted(samples.items()):
        sample_run_dir = counts_dir / sample
        command = [
            args.cellranger_atac_bin,
            "count",
            f"--id={sample}",
            f"--reference={reference}",
            f"--fastqs={fastq_dir}",
            f"--sample={sample}",
            *common_flags,
        ]
        run_command(command, cwd=counts_dir)

        fragments = sample_run_dir / "outs" / "fragments.tsv.gz"
        cells = sample_run_dir / "outs" / "singlecell.csv"
        if not fragments.exists():
            raise SystemExit(f"Expected count output missing: {fragments}")
        if not cells.exists():
            raise SystemExit(f"Expected count output missing: {cells}")

        aggregation_rows.append(
            {
                "library_id": sample,
                "fragments": str(fragments),
                "cells": str(cells),
            }
        )
        manifest.append(
            {
                "sample": sample,
                "fastqs": files,
                "count_dir": str(sample_run_dir),
                "fragments": str(fragments),
                "cells": str(cells),
            }
        )

    write_json(results_dir / "samples.json", manifest)
    write_aggregation_csv(aggregation_csv, aggregation_rows)

    if run_aggr and len(aggregation_rows) >= 2:
        combined_dir.mkdir(parents=True, exist_ok=True)
        command = [
            args.cellranger_atac_bin,
            "aggr",
            "--id=combined",
            f"--csv={aggregation_csv}",
            f"--reference={reference}",
            *common_flags,
        ]
        run_command(command, cwd=results_dir)
    elif run_aggr:
        print(
            f"Skipping aggr because only {len(aggregation_rows)} sample was discovered."
        )
    else:
        print("Skipping aggr because run_aggr=false.")

    print(f"Discovered samples: {', '.join(sorted(samples))}")
    print(f"Counts written under: {counts_dir}")
    print(f"Aggregation CSV: {aggregation_csv}")
    if run_aggr and len(aggregation_rows) >= 2:
        print(f"Aggregated output: {results_dir / 'combined'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
