#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


PLACEHOLDER_PATTERNS = (
    re.compile(r"^example", re.IGNORECASE),
    re.compile(r"^test", re.IGNORECASE),
)
PLACEHOLDER_INDEXES = {"AAAAAAAAAA", "TTTTTTTTTT", "CCCCCCCCCC", "GGGGGGGGGG"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint AVITI/Illumina flowcell samplesheets.")
    parser.add_argument("--flowcell-samplesheet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def lint_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    section = ""
    header: list[str] | None = None
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for line_number, raw_row in enumerate(csv.reader(handle), start=1):
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
            padded = raw_row + [""] * max(0, len(header) - len(raw_row))
            row = {key.lower(): value.strip() for key, value in zip(header, padded)}
            sample = row.get("samplename") or row.get("sample_name") or row.get("sample_id") or ""
            index1 = row.get("index1") or row.get("index") or ""
            index2 = row.get("index2") or row.get("index2") or ""
            issues: list[str] = []
            if any(pattern.search(sample) for pattern in PLACEHOLDER_PATTERNS):
                issues.append("placeholder_sample_name")
            if index1.upper() in PLACEHOLDER_INDEXES or index2.upper() in PLACEHOLDER_INDEXES:
                issues.append("placeholder_index")
            if not sample:
                issues.append("missing_sample_name")
            if issues:
                rows.append(
                    {
                        "line": str(line_number),
                        "sample": sample,
                        "index1": index1,
                        "index2": index2,
                        "issues": ";".join(issues),
                    }
                )
    return rows


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["line", "sample", "index1", "index2", "issues"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    rows = lint_rows(args.flowcell_samplesheet.resolve())
    write_report(args.output, rows)
    if rows:
        print(f"[warning] Manifest lint found {len(rows)} suspicious row(s). Report: {args.output}")
        for row in rows[:10]:
            print(f"[warning] line {row['line']}: sample={row['sample']} issues={row['issues']}")
        print("[warning] Placeholder rows can produce empty FASTQs and cause nf-core read-group generation to fail.")
    else:
        print(f"[info] Manifest lint found no suspicious rows. Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
