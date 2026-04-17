#!/usr/bin/env python3
from __future__ import annotations

from registry_common import (
    enabled_datasets,
    load_existing_samples,
    load_registry,
    parse_bool,
    resolve_dataset_path,
    sample_key,
    scan_idat_pairs,
    write_samples,
)


def main() -> int:
    doc = load_registry()
    existing = {sample_key(row): row for row in load_existing_samples()}
    merged_rows = []

    for dataset in enabled_datasets(doc):
        dataset_id = str(dataset.get("dataset_id", "")).strip()
        if not dataset_id:
            continue
        batch = str(dataset.get("batch", "")).strip() or dataset_id
        for pair in scan_idat_pairs(resolve_dataset_path(dataset)):
            key = (dataset_id, pair["idat_basename"])
            previous = existing.get(key, {})
            sample_id = previous.get("sample_id") or f"{dataset_id}__{pair['SentrixBarcode'] or PathSafe(pair['idat_basename'])}"
            merged_rows.append(
                {
                    "sample_id": sample_id,
                    "dataset_id": dataset_id,
                    "group": previous.get("group", ""),
                    "subgroup": previous.get("subgroup", ""),
                    "batch": previous.get("batch", batch),
                    "analysis_set": previous.get("analysis_set", "main"),
                    "include": previous.get("include", "true" if parse_bool(dataset.get("enabled", True)) else "false"),
                    "exclude_reason": previous.get("exclude_reason", ""),
                    "SentrixBarcode": pair["SentrixBarcode"],
                    "SentrixPosition": pair["SentrixPosition"],
                    "idat_dir": pair["idat_dir"],
                    "idat_basename": pair["idat_basename"],
                    "sex": previous.get("sex", ""),
                    "age": previous.get("age", ""),
                    "notes": previous.get("notes", ""),
                }
            )

    merged_rows.sort(key=lambda row: (row["dataset_id"], row["sample_id"]))
    write_samples(merged_rows)
    print(f"[INFO] Wrote {len(merged_rows)} sample rows to config/samples.csv")
    return 0


def PathSafe(path: str) -> str:
    return path.replace("/", "_").replace(" ", "_")


if __name__ == "__main__":
    raise SystemExit(main())
