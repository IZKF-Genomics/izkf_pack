#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - user-facing environment error
    raise SystemExit("PyYAML is required. Run this command inside the template Pixi environment.") from exc

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.table import Table
except ImportError:
    Console = None
    Panel = None
    Confirm = None
    Prompt = None
    Table = None


HIDDEN_COLUMNS = {"fastq_1", "fastq_2", "strandedness"}
console = Console(highlight=False) if Console is not None else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure and validate miRNA differential models.")
    parser.add_argument("--samplesheet", required=True)
    parser.add_argument("--counts-file", required=True)
    parser.add_argument("--config", default="config/analysis.yaml")
    parser.add_argument("--samples-out", default="config/samples.csv")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--configure", action="store_true")
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--auto-if-missing", action="store_true")
    return parser.parse_args()


def say(message: str) -> None:
    if console is not None:
        console.print(message)
    else:
        print(re.sub(r"\[/?[A-Za-z ]+\]", "", message))


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames or []
    if not columns or not rows:
        raise ValueError(f"CSV is empty: {path}")
    return columns, rows


def clean(value: object) -> str:
    return str(value or "").strip()


def natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def infer_sample_metadata(sample_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    inferred: list[dict[str, str]] = []
    for row in sample_rows:
        sample = clean(row.get("sample"))
        parts = sample.split("_")
        if len(parts) < 3 or any(not part for part in parts):
            raise ValueError(
                f"Cannot safely infer group, time, and subject from sample '{sample}'. "
                "Use underscore-separated names ending in _<time>_<subject>, or create config/samples.csv manually."
            )
        inferred.append(
            {
                "sample": sample,
                "include": "true",
                "group": "_".join(parts[:-2]),
                "time": parts[-2],
                "subject": parts[-1],
            }
        )
    return inferred


def preferred_reference(values: list[str], preferred: tuple[str, ...]) -> str:
    lookup = {value.lower(): value for value in values}
    for candidate in preferred:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return sorted(values, key=natural_key)[0]


def default_configuration(
    metadata: list[dict[str, str]],
    requested_base_group: str | None = None,
    requested_base_time: str | None = None,
) -> dict[str, Any]:
    groups = sorted({row["group"] for row in metadata}, key=natural_key)
    times = sorted({row["time"] for row in metadata}, key=natural_key)
    if len(groups) != 2 or len(times) != 2:
        raise ValueError(
            "Automatic longitudinal configuration requires exactly two groups and two time levels; "
            f"found groups={groups}, times={times}. Edit config/analysis.yaml after creating sample metadata."
        )
    base_group = requested_base_group or preferred_reference(groups, ("Kontroll", "Control", "WT", "Vehicle"))
    if base_group not in groups:
        raise ValueError(f"Reference group '{base_group}' is absent from sample metadata.")
    target_group = next(value for value in groups if value != base_group)
    base_time = requested_base_time or preferred_reference(times, ("0h", "0", "baseline", "pre"))
    if base_time not in times:
        raise ValueError(f"Reference time '{base_time}' is absent from sample metadata.")
    target_time = next(value for value in times if value != base_time)
    slug = lambda value: re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return {
        "schema_version": 1,
        "analysis": {
            "primary_contrast": "group_time_interaction",
            "alpha": 0.05,
            "lfc_threshold": 1.0,
            "min_count": 10,
            "min_samples": max(2, min(Counter((row["group"], row["time"]) for row in metadata).values())),
            "top_labels": 12,
            "top_heatmap": 30,
        },
        "reference_levels": {"group": base_group, "time": base_time},
        "contrasts": [
            {
                "id": "group_time_interaction",
                "label": f"Differential change: {target_group} versus {base_group}",
                "type": "interaction",
                "target_group": target_group,
                "base_group": base_group,
                "target_time": target_time,
                "base_time": base_time,
            },
            {
                "id": f"{slug(target_group)}_vs_{slug(base_group)}_at_{slug(target_time)}",
                "label": f"{target_group} versus {base_group} at {target_time}",
                "type": "two_group",
                "target_group": target_group,
                "base_group": base_group,
                "at_time": target_time,
            },
            {
                "id": f"{slug(target_group)}_{slug(target_time)}_vs_{slug(base_time)}",
                "label": f"{target_group}: {target_time} versus {base_time}",
                "type": "paired_time",
                "group": target_group,
                "target_time": target_time,
                "base_time": base_time,
            },
            {
                "id": f"{slug(base_group)}_{slug(target_time)}_vs_{slug(base_time)}",
                "label": f"{base_group}: {target_time} versus {base_time}",
                "type": "paired_time",
                "group": base_group,
                "target_time": target_time,
                "base_time": base_time,
            },
        ],
        "supplementary": {"analyze_hairpin": False},
    }


def write_metadata(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample", "include", "group", "time", "subject"])
        writer.writeheader()
        writer.writerows(rows)


def write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")


def print_metadata(rows: list[dict[str, str]]) -> None:
    if Table is None or console is None:
        say("sample\tgroup\ttime\tsubject")
        for row in rows:
            say("\t".join(row[key] for key in ("sample", "group", "time", "subject")))
        return
    table = Table(title="Analysis-facing sample metadata", header_style="bold cyan")
    for column in ("sample", "group", "time", "subject"):
        table.add_column(column)
    for row in rows:
        table.add_row(*(row[column] for column in ("sample", "group", "time", "subject")))
    console.print(table)


def configure(samplesheet: Path, config_path: Path, samples_path: Path, interactive: bool) -> None:
    columns, sample_rows = read_csv(samplesheet)
    if "sample" not in columns:
        raise ValueError("Samplesheet must contain a 'sample' column.")
    metadata = infer_sample_metadata(sample_rows)
    print_metadata(metadata)
    config = default_configuration(metadata)
    refs = dict(config["reference_levels"])
    if interactive:
        accepted = Confirm.ask("Use the inferred group/time/subject metadata?", default=True) if Confirm else input(
            "Use the inferred group/time/subject metadata? [Y/n]: "
        ).strip().lower() not in {"n", "no"}
        if not accepted:
            raise ValueError("Configuration cancelled. Create config/samples.csv manually and run --validate.")
        groups = sorted({row["group"] for row in metadata}, key=natural_key)
        times = sorted({row["time"] for row in metadata}, key=natural_key)
        if Prompt is not None:
            refs["group"] = Prompt.ask("Reference group", choices=groups, default=refs["group"])
            refs["time"] = Prompt.ask("Reference time", choices=times, default=refs["time"])
            config = default_configuration(metadata, refs["group"], refs["time"])
    write_metadata(samples_path, metadata)
    write_config(config_path, config)
    say(f"[green]Wrote {samples_path} and {config_path}.[/green]")
    say("Review both files, then run ./run.sh --validate before analysis.")


def parse_bool(value: object) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y"}


def inspect_counts(path: Path, samples: set[str]) -> tuple[str, int, int, set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("Counts CSV is empty.") from exc
        if len(header) < 2:
            raise ValueError("Counts CSV must have an identifier column and at least one data column.")
        row_ids: list[str] = []
        n_rows = 0
        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(f"Counts CSV row {line_number} has {len(row)} fields; expected {len(header)}.")
            row_ids.append(clean(row[0]))
            for value in row[1:]:
                try:
                    number = float(value)
                except ValueError as exc:
                    raise ValueError(f"Counts CSV contains a non-numeric value at row {line_number}.") from exc
                if not math.isfinite(number) or number < 0 or number != round(number):
                    raise ValueError(f"Counts must be finite non-negative integers; invalid value at row {line_number}.")
            n_rows += 1
    header_ids = {clean(value) for value in header[1:]}
    row_id_set = set(row_ids)
    if samples <= row_id_set:
        return "samples_by_rows", n_rows, len(header) - 1, row_id_set
    if samples <= header_ids:
        return "features_by_rows", n_rows, len(header) - 1, header_ids
    missing_rows = sorted(samples - row_id_set)
    missing_cols = sorted(samples - header_ids)
    raise ValueError(
        "Sample names do not match either axis of the counts CSV. "
        f"Missing from rows: {missing_rows[:5]}; missing from columns: {missing_cols[:5]}."
    )


def validate(samplesheet: Path, counts_file: Path, config_path: Path, samples_path: Path) -> None:
    sheet_columns, sheet_rows = read_csv(samplesheet)
    if "sample" not in sheet_columns:
        raise ValueError("Samplesheet must contain a 'sample' column.")
    sheet_samples = [clean(row["sample"]) for row in sheet_rows]
    if len(sheet_samples) != len(set(sheet_samples)):
        raise ValueError("Samplesheet contains duplicate sample names.")

    metadata_columns, metadata = read_csv(samples_path)
    required = {"sample", "include", "group", "time", "subject"}
    missing_columns = sorted(required - set(metadata_columns))
    if missing_columns:
        raise ValueError("config/samples.csv is missing columns: " + ", ".join(missing_columns))
    included = [row for row in metadata if parse_bool(row["include"])]
    if not included:
        raise ValueError("No samples are enabled in config/samples.csv.")
    for row in included:
        for key in ("sample", "group", "time", "subject"):
            if not clean(row[key]):
                raise ValueError(f"Enabled sample has an empty {key} value: {row}")
    included_names = [clean(row["sample"]) for row in included]
    if len(included_names) != len(set(included_names)):
        raise ValueError("config/samples.csv contains duplicate enabled sample names.")
    missing_sheet = sorted(set(included_names) - set(sheet_samples))
    if missing_sheet:
        raise ValueError("Configured samples absent from nf-core samplesheet: " + ", ".join(missing_sheet))

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("analysis.yaml must be a mapping with schema_version: 1.")
    analysis = config.get("analysis") or {}
    for key in ("alpha", "lfc_threshold", "min_count", "min_samples", "top_labels", "top_heatmap"):
        if key not in analysis:
            raise ValueError(f"analysis.yaml is missing analysis.{key}.")
    if not 0 < float(analysis["alpha"]) < 1:
        raise ValueError("analysis.alpha must be between 0 and 1.")
    contrasts = config.get("contrasts") or []
    if not contrasts:
        raise ValueError("At least one contrast is required.")
    ids = [clean(item.get("id")) for item in contrasts]
    if any(not re.fullmatch(r"[A-Za-z0-9_]+", value) for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Contrast ids must be unique and contain only letters, numbers, and underscores.")
    primary_contrast = clean(analysis.get("primary_contrast"))
    if primary_contrast not in ids:
        raise ValueError("analysis.primary_contrast must name one configured contrast.")
    supported = {"interaction", "two_group", "paired_time"}
    if any(item.get("type") not in supported for item in contrasts):
        raise ValueError(f"Contrast type must be one of {sorted(supported)}.")

    groups = {row["group"] for row in included}
    times = {row["time"] for row in included}
    subject_groups: dict[str, set[str]] = defaultdict(set)
    subject_times: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in included:
        subject_groups[row["subject"]].add(row["group"])
        subject_times[(row["group"], row["subject"])].add(row["time"])
    for contrast in contrasts:
        kind = contrast["type"]
        if kind == "interaction":
            required_groups = {contrast["base_group"], contrast["target_group"]}
            required_times = {contrast["base_time"], contrast["target_time"]}
            if not required_groups <= groups or not required_times <= times:
                raise ValueError(f"Interaction contrast {contrast['id']} refers to absent group/time levels.")
            incomplete = [
                f"{group}:{subject}"
                for (group, subject), seen in subject_times.items()
                if group in required_groups and not required_times <= seen
            ]
            if incomplete:
                raise ValueError("Interaction requires complete paired time points; incomplete subjects: " + ", ".join(incomplete))
        elif kind == "paired_time":
            group = contrast["group"]
            required_times = {contrast["base_time"], contrast["target_time"]}
            relevant = {key: seen for key, seen in subject_times.items() if key[0] == group}
            if not relevant or any(not required_times <= seen for seen in relevant.values()):
                raise ValueError(f"Paired contrast {contrast['id']} does not have complete subject pairs.")
        else:
            at_time = contrast["at_time"]
            required_groups = {contrast["base_group"], contrast["target_group"]}
            seen_groups = {row["group"] for row in included if row["time"] == at_time}
            if not required_groups <= seen_groups:
                raise ValueError(f"Two-group contrast {contrast['id']} lacks one group at {at_time}.")

    orientation, n_rows, n_columns, count_samples = inspect_counts(counts_file, set(included_names))
    extra = sorted(count_samples - set(included_names))
    say(
        f"[green]Validation passed.[/green] {len(included)} samples, {len(contrasts)} contrasts, "
        f"counts orientation={orientation}, matrix={n_rows}x{n_columns}, extra count samples={len(extra)}."
    )


def main() -> int:
    args = parse_args()
    samplesheet = Path(args.samplesheet).expanduser().resolve()
    counts_file = Path(args.counts_file).expanduser().resolve()
    config_path = Path(args.config)
    samples_path = Path(args.samples_out)
    try:
        if args.configure:
            configure(samplesheet, config_path, samples_path, interactive=True)
        elif args.auto_if_missing:
            if not config_path.exists() or not samples_path.exists():
                configure(samplesheet, config_path, samples_path, interactive=False)
        else:
            if not config_path.exists() or not samples_path.exists():
                raise ValueError("Configuration is missing. Run ./run.sh --configure first.")
            validate(samplesheet, counts_file, config_path, samples_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        say(f"[bold red]Configuration error:[/bold red] {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
