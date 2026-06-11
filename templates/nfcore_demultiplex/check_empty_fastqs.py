#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import re
from pathlib import Path


FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz", ".fastq", ".fq")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report empty FASTQ files from an nf-core/demultiplex run."
    )
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--work-dir", default="work", type=Path)
    parser.add_argument("--flowcell-samplesheet", required=True, type=Path)
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit non-zero when empty FASTQs are detected.",
    )
    return parser.parse_args()


def fastq_paths(*roots: Path) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.name.endswith(FASTQ_SUFFIXES):
                resolved = path.resolve()
                if resolved not in seen:
                    paths.append(resolved)
                    seen.add(resolved)
    return sorted(paths)


def first_fastq_line(path: Path) -> str:
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="ascii", errors="replace") as handle:
                return (handle.readline() or "").strip()
        with path.open(encoding="ascii", errors="replace") as handle:
            return (handle.readline() or "").strip()
    except EOFError:
        return ""


def read_name(path: Path) -> str:
    name = path.name
    for suffix in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    match = re.search(r"(.+)_R([12])(?:_|\.|$)", name)
    if match:
        return f"R{match.group(2)}"
    return ""


def sample_name(path: Path) -> str:
    parent = path.parent.name
    if parent and parent not in {"Samples", "DefaultProject"}:
        return parent
    name = path.name
    for suffix in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = re.sub(r"_R[12].*$", "", name)
    name = re.sub(r"_S\d+_L\d{3}$", "", name)
    return name


def manifest_samples(path: Path) -> set[str]:
    samples: set[str] = set()
    section = ""
    header: list[str] | None = None
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for raw_row in csv.reader(handle):
            if not raw_row or not any(cell.strip() for cell in raw_row):
                continue
            first = raw_row[0].strip()
            if first.startswith("#"):
                continue
            if first.startswith("[") and first.endswith("]"):
                section = first.strip("[]").lower()
                header = None
                continue
            if section not in {"samples", "data"}:
                continue
            if header is None:
                header = [cell.strip() for cell in raw_row]
                continue
            row = raw_row + [""] * max(0, len(header) - len(raw_row))
            values = {key.lower(): value.strip() for key, value in zip(header, row)}
            sample = values.get("samplename") or values.get("sample_name") or values.get("sample_id")
            if sample:
                samples.add(sample)
    return samples


def detect_empty_fastqs(paths: list[Path], manifest_sample_names: set[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        first_line = first_fastq_line(path)
        if first_line.startswith("@"):
            continue
        sample = sample_name(path)
        reason = "no reads matched sample indexes"
        if sample and sample not in manifest_sample_names and sample.lower() == "unassigned":
            reason = "unassigned reads output is empty"
        rows.append(
            {
                "sample": sample,
                "read": read_name(path),
                "fastq_path": str(path),
                "size_bytes": str(path.stat().st_size),
                "likely_reason": reason,
            }
        )
    return rows


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["sample", "read", "fastq_path", "size_bytes", "likely_reason"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    work_dir = args.work_dir.resolve()
    output = args.output or (results_dir / "empty_fastq_report.csv")
    rows = detect_empty_fastqs(
        fastq_paths(results_dir, work_dir),
        manifest_samples(args.flowcell_samplesheet.resolve()),
    )
    write_report(output, rows)
    if rows:
        samples = sorted({row["sample"] for row in rows if row["sample"]})
        print(f"[error] Empty FASTQ files detected: {len(rows)} file(s).")
        if samples:
            print("[error] Affected sample(s): " + ", ".join(samples))
        print(f"[error] Report written to: {output}")
        print("[error] This usually means the sample indexes in flowcell_samplesheet.csv did not match reads in the run, or a placeholder/sample row has no reads.")
        print("[error] Fix the Index1/Index2 values or comment/remove the affected sample rows, then rerun with -resume.")
        return 1 if args.fail_on_empty else 0
    print(f"[info] No empty FASTQ files detected. Report written to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
