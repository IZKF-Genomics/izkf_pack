#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
COMMAND_MARKERS = {
    "bases2fastq": ("bases2fastq",),
    "bclconvert": ("bcl-convert", "bclconvert"),
    "bcl2fastq": ("bcl2fastq",),
    "cellranger": ("cellranger mkfastq",),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recover demultiplexed FASTQs from a successful nf-core/demultiplex work directory."
    )
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--flowcell-id", required=True)
    parser.add_argument("--demultiplexer", required=True)
    parser.add_argument("--output", default="recovered_demultiplex_fastqs.csv", type=Path)
    return parser.parse_args()


def command_markers(demultiplexer: str) -> tuple[str, ...]:
    normalized = demultiplexer.strip().lower()
    return COMMAND_MARKERS.get(normalized, (normalized,))


def is_successful_demux_dir(path: Path, markers: tuple[str, ...]) -> bool:
    command = path / ".command.sh"
    exitcode = path / ".exitcode"
    if not command.is_file() or not exitcode.is_file():
        return False
    if exitcode.read_text(encoding="utf-8", errors="replace").strip() != "0":
        return False
    text = command.read_text(encoding="utf-8", errors="replace").lower()
    return any(marker.lower() in text for marker in markers)


def find_successful_demux_dirs(work_dir: Path, demultiplexer: str) -> list[Path]:
    markers = command_markers(demultiplexer)
    candidates: list[Path] = []
    for command in work_dir.glob("*/*/.command.sh"):
        directory = command.parent
        if is_successful_demux_dir(directory, markers):
            candidates.append(directory)
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


def is_demux_fastq(path: Path) -> bool:
    name = path.name
    if not name.endswith(FASTQ_SUFFIXES):
        return False
    lowered = str(path).lower()
    return ".fastp." not in lowered and "fastqc" not in lowered and "falco" not in lowered


def demux_fastqs(directory: Path) -> list[Path]:
    return sorted(path.resolve() for path in directory.rglob("*") if path.is_file() and is_demux_fastq(path))


def sanitize_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return text.strip("._") or "flowcell"


def safe_hardlink(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        destination.unlink()
    elif destination.exists():
        return "kept_existing"
    destination.hardlink_to(source)
    return "hardlinked"


def write_report(report_path: Path, rows: list[dict[str, str]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_fastq", "recovered_fastq", "status"],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    work_dir = args.work_dir.resolve()
    if not work_dir.exists():
        raise SystemExit(f"[error] work directory does not exist: {work_dir}")

    for candidate in find_successful_demux_dirs(work_dir, args.demultiplexer):
        fastqs = demux_fastqs(candidate)
        if not fastqs:
            continue
        target_dir = results_dir / sanitize_name(args.flowcell_id)
        rows: list[dict[str, str]] = []
        for fastq in fastqs:
            destination = target_dir / fastq.name
            status = safe_hardlink(fastq, destination)
            rows.append(
                {
                    "source_fastq": str(fastq),
                    "recovered_fastq": str(destination),
                    "status": status,
                }
            )
        output = args.output
        if not output.is_absolute():
            output = results_dir / output
        write_report(output, rows)
        print(f"[info] recovered {len(rows)} FASTQ file(s) from {candidate}")
        print(f"[info] recovery report: {output}")
        return 0

    raise SystemExit(
        "[error] no successful demultiplexer work directory with FASTQ files was found. "
        "The nf-core failure was not recoverable from work/."
    )


if __name__ == "__main__":
    raise SystemExit(main())
