from __future__ import annotations

import csv
import re
import tomllib
from pathlib import Path
from typing import Any


IDAT_RED_SUFFIX = "_Red.idat"
IDAT_GRN_SUFFIX = "_Grn.idat"
PAIR_RE = re.compile(r"^(?P<basename>.+)_(?P<channel>Red|Grn)\.idat$")
SENTRIX_RE = re.compile(r"^(?P<barcode>.+)_(?P<position>R\d\dC\d\d)$")


def workspace_root() -> Path:
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return workspace_root() / "config" / "datasets.toml"


def samples_path() -> Path:
    return workspace_root() / "config" / "samples.csv"


def load_registry() -> Any:
    with config_path().open("rb") as handle:
        return tomllib.load(handle)


def save_registry(doc: Any) -> None:
    config_path().write_text(dump_registry(doc), encoding="utf-8")


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "t", "1", "yes", "y"}:
        return True
    if text in {"false", "f", "0", "no", "n"}:
        return False
    return default


def resolve_dataset_path(dataset: dict[str, Any]) -> Path:
    path = str(dataset.get("path", "")).strip()
    if not path:
        raise ValueError(f"Dataset {dataset.get('dataset_id', '<unknown>')} is missing a path")
    p = Path(path)
    if p.is_absolute():
        return p
    return (workspace_root() / p).resolve()


def enabled_datasets(doc: Any) -> list[dict[str, Any]]:
    datasets = doc.get("datasets", [])
    out: list[dict[str, Any]] = []
    for dataset in datasets:
        if parse_bool(dataset.get("enabled", True), default=True):
            out.append(dataset)
    return out


def upsert_dataset(doc: Any, dataset_id: str, payload: dict[str, Any]) -> None:
    datasets = doc.setdefault("datasets", [])
    for entry in datasets:
        if str(entry.get("dataset_id", "")).strip() == dataset_id:
            for key, value in payload.items():
                entry[key] = value
            return
    table: dict[str, Any] = {"dataset_id": dataset_id}
    for key, value in payload.items():
        table[key] = value
    datasets.append(table)


def scan_idat_pairs(root: Path) -> list[dict[str, str]]:
    pairs: dict[str, dict[str, str]] = {}
    for path in sorted(root.rglob("*.idat")):
        match = PAIR_RE.match(path.name)
        if match is None:
            continue
        basename = match.group("basename")
        record = pairs.setdefault(str(path.parent / basename), {"red": "", "grn": ""})
        channel = match.group("channel").lower()
        record[channel] = str(path)

    rows: list[dict[str, str]] = []
    for basename, record in sorted(pairs.items()):
        root_name = Path(basename).name
        sentrix = SENTRIX_RE.match(root_name)
        barcode = sentrix.group("barcode") if sentrix else ""
        position = sentrix.group("position") if sentrix else ""
        rows.append(
            {
                "idat_basename": basename,
                "idat_dir": str(Path(basename).parent),
                "SentrixBarcode": barcode,
                "SentrixPosition": position,
                "red_path": record["red"],
                "grn_path": record["grn"],
            }
        )
    return rows


def load_existing_samples() -> list[dict[str, str]]:
    path = samples_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_samples(rows: list[dict[str, Any]]) -> None:
    path = samples_path()
    fieldnames = [
        "sample_id",
        "dataset_id",
        "group",
        "subgroup",
        "batch",
        "analysis_set",
        "include",
        "exclude_reason",
        "SentrixBarcode",
        "SentrixPosition",
        "idat_dir",
        "idat_basename",
        "sex",
        "age",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def sample_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("dataset_id", "")), str(row.get("idat_basename", "")))


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _dump_section(lines: list[str], name: str, payload: dict[str, Any]) -> None:
    if not payload:
        return
    lines.append(f"[{name}]")
    for key, value in payload.items():
        if isinstance(value, list):
            formatted = ", ".join(_format_scalar(item) for item in value)
            lines.append(f"{key} = [{formatted}]")
        else:
            lines.append(f"{key} = {_format_scalar(value)}")
    lines.append("")


def dump_registry(doc: dict[str, Any]) -> str:
    lines: list[str] = []
    ordered_sections = [
        "project",
        "processing",
        "filter",
        "batch_correction",
        "cell_counts",
        "embeddings",
        "dmr",
        "enrichment",
        "drilldown",
    ]
    for section in ordered_sections:
        _dump_section(lines, section, doc.get(section, {}))
    for dataset in doc.get("datasets", []):
        lines.append("[[datasets]]")
        for key, value in dataset.items():
            if isinstance(value, list):
                formatted = ", ".join(_format_scalar(item) for item in value)
                lines.append(f"{key} = [{formatted}]")
            else:
                lines.append(f"{key} = {_format_scalar(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
