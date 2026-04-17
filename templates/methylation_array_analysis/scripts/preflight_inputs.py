#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path

from registry_common import samples_path, workspace_root


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() not in {"false", "f", "0", "no", "n"}


def main() -> int:
    sample_file = samples_path()
    if not sample_file.exists():
        raise SystemExit("config/samples.csv is missing. Run pixi run sync-samples first.")

    results_dir = workspace_root() / "results" / "tables"
    results_dir.mkdir(parents=True, exist_ok=True)
    rows_out = []
    missing = []

    with sample_file.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not parse_bool(row.get("include", "true")):
                continue
            basename = row.get("idat_basename", "").strip()
            if not basename and row.get("SentrixBarcode") and row.get("SentrixPosition"):
                base_dir = row.get("idat_dir", "").strip()
                basename = str(Path(base_dir) / f"{row['SentrixBarcode']}_{row['SentrixPosition']}")
            red = f"{basename}_Red.idat"
            grn = f"{basename}_Grn.idat"
            red_exists = Path(red).exists()
            grn_exists = Path(grn).exists()
            rows_out.append(
                {
                    "sample_id": row.get("sample_id", ""),
                    "dataset_id": row.get("dataset_id", ""),
                    "idat_basename": basename,
                    "red_exists": str(red_exists).lower(),
                    "grn_exists": str(grn_exists).lower(),
                }
            )
            if not (red_exists and grn_exists):
                missing.append(row.get("sample_id", "<unknown>"))

    out_file = results_dir / "idat_preflight.csv"
    with out_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_out[0].keys()) if rows_out else ["sample_id", "dataset_id", "idat_basename", "red_exists", "grn_exists"])
        writer.writeheader()
        writer.writerows(rows_out)

    if missing:
        raise SystemExit(f"Missing IDAT pairs for: {', '.join(missing)}")
    print(f"[INFO] Wrote {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
