#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

try:
    from rich.console import Console
    from rich.prompt import Confirm
    from rich.table import Table
except ImportError:  # pragma: no cover
    Console = None
    Confirm = None
    Table = None


console = Console(highlight=False) if Console is not None else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure and validate paired gene-level interaction models.")
    parser.add_argument("--samplesheet", required=True)
    parser.add_argument("--salmon-dir", required=True)
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


def parse_bool(value: object) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y"}


def canonical_condition(value: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", value.lower())
    aliases = {
        "control": "Control",
        "ctrl": "Control",
        "baseline": "Control",
        "sinusrhythm": "SinusRhythm",
        "sr": "SinusRhythm",
        "atrialfibrillation": "AtrialFibrillation",
        "af": "AtrialFibrillation",
    }
    return aliases.get(key, re.sub(r"[^A-Za-z0-9]+", "", value) or value)


def infer_metadata(columns: list[str], rows: list[dict[str, str]]) -> list[dict[str, str]]:
    inferred: list[dict[str, str]] = []
    for row in rows:
        sample = clean(row.get("sample"))
        if not sample:
            raise ValueError("Samplesheet contains an empty sample name.")
        subject = clean(row.get("id") or row.get("subject"))
        group_value = clean(row.get("group"))
        genotype = clean(row.get("genotype"))
        condition = clean(row.get("condition"))
        if group_value and "_" in group_value:
            group_genotype, group_condition = group_value.split("_", 1)
            genotype = genotype or group_genotype
            condition = condition or group_condition
        match = re.match(r"^([A-Za-z]+)(\d+)_([^/]+)$", sample)
        if match:
            genotype = genotype or match.group(1)
            subject = subject or f"{match.group(1)}{match.group(2)}"
            condition = condition or match.group(3)
        if not (genotype and subject and condition):
            raise ValueError(
                f"Cannot infer genotype, subject, and condition for '{sample}'. "
                "Provide genotype/condition/id columns or use names such as WT1_Control."
            )
        inferred.append(
            {
                "sample": sample,
                "include": "true",
                "genotype": genotype,
                "condition": canonical_condition(condition),
                "subject": subject,
            }
        )
    return inferred


def choose(values: set[str], preferred: tuple[str, ...], label: str) -> str:
    lookup = {re.sub(r"[^a-z0-9]", "", value.lower()): value for value in values}
    for candidate in preferred:
        key = re.sub(r"[^a-z0-9]", "", candidate.lower())
        if key in lookup:
            return lookup[key]
    raise ValueError(f"Cannot identify {label} from levels: {sorted(values)}")


def interaction(identifier: str, label: str, base_group: str, target_group: str, base: str, target: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "type": "interaction",
        "base_group": base_group,
        "target_group": target_group,
        "base_condition": base,
        "target_condition": target,
    }


def paired(identifier: str, label: str, group: str, base: str, target: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "type": "paired_condition",
        "group": group,
        "base_condition": base,
        "target_condition": target,
    }


def default_configuration(metadata: list[dict[str, str]]) -> dict[str, Any]:
    groups = {row["genotype"] for row in metadata}
    conditions = {row["condition"] for row in metadata}
    if len(groups) != 2:
        raise ValueError(f"Automatic configuration requires two genotypes; found {sorted(groups)}")
    wt = choose(groups, ("WT", "Control", "Reference"), "reference genotype")
    ttn = next(value for value in groups if value != wt)
    control = choose(conditions, ("Control", "Baseline"), "control condition")
    sr = choose(conditions, ("SinusRhythm", "SR"), "normal-stimulation condition")
    af = choose(conditions, ("AtrialFibrillation", "AF"), "AF-like condition")
    min_replicates = min(Counter((row["genotype"], row["condition"]) for row in metadata).values())
    return {
        "schema_version": 1,
        "analysis": {
            "primary_contrast": "ttn_af_response_interaction",
            "alpha": 0.05,
            "lfc_threshold": 1.0,
            "min_count": 10,
            "min_samples": max(2, min_replicates),
            "top_labels": 15,
            "top_heatmap": 30,
            "pathway_analysis": True,
            "pathway_padj": 0.05,
        },
        "reference_levels": {"genotype": wt, "condition": control},
        "contrasts": [
            {
                "id": "baseline_ttn",
                "label": f"Baseline genotype effect: {ttn} versus {wt}",
                "type": "two_group",
                "base_group": wt,
                "target_group": ttn,
                "at_condition": control,
            },
            paired("wt_sr_vs_control", f"{wt}: normal stimulation versus control", wt, control, sr),
            paired("ttn_sr_vs_control", f"{ttn}: normal stimulation versus control", ttn, control, sr),
            interaction("ttn_sr_response_interaction", f"Genotype modification of normal-stimulation response: {ttn} versus {wt}", wt, ttn, control, sr),
            paired("wt_af_vs_sr", f"{wt}: AF-like versus normal stimulation", wt, sr, af),
            paired("ttn_af_vs_sr", f"{ttn}: AF-like versus normal stimulation", ttn, sr, af),
            interaction("ttn_af_response_interaction", f"Genotype modification of AF-like response: {ttn} versus {wt}", wt, ttn, sr, af),
        ],
    }


def write_metadata(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample", "include", "genotype", "condition", "subject"])
        writer.writeheader()
        writer.writerows(rows)


def write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")


def show_metadata(rows: list[dict[str, str]]) -> None:
    if Table is None or console is None:
        say("sample\tgenotype\tcondition\tsubject")
        for row in rows:
            say("\t".join(row[key] for key in ("sample", "genotype", "condition", "subject")))
        return
    table = Table(title="Analysis-facing sample metadata", header_style="bold cyan")
    for column in ("sample", "genotype", "condition", "subject"):
        table.add_column(column)
    for row in rows:
        table.add_row(*(row[column] for column in ("sample", "genotype", "condition", "subject")))
    console.print(table)


def configure(samplesheet: Path, config_path: Path, samples_path: Path, interactive: bool) -> None:
    columns, rows = read_csv(samplesheet)
    if "sample" not in columns:
        raise ValueError("Samplesheet must contain a sample column.")
    metadata = infer_metadata(columns, rows)
    show_metadata(metadata)
    if interactive:
        accepted = Confirm.ask("Use the inferred metadata and seven predefined contrasts?", default=True) if Confirm else True
        if not accepted:
            raise ValueError("Configuration cancelled. Create config files manually and run --validate.")
    write_metadata(samples_path, metadata)
    write_config(config_path, default_configuration(metadata))
    say(f"[green]Wrote {samples_path} and {config_path}.[/green]")


def require_keys(item: dict[str, Any], keys: tuple[str, ...], label: str) -> None:
    missing = [key for key in keys if not clean(item.get(key))]
    if missing:
        raise ValueError(f"{label} is missing: {', '.join(missing)}")


def validate(samplesheet: Path, salmon_dir: Path, config_path: Path, samples_path: Path) -> None:
    sheet_columns, sheet_rows = read_csv(samplesheet)
    if "sample" not in sheet_columns:
        raise ValueError("Samplesheet must contain a sample column.")
    sheet_samples = [clean(row["sample"]) for row in sheet_rows]
    if len(sheet_samples) != len(set(sheet_samples)):
        raise ValueError("Samplesheet contains duplicate sample names.")
    metadata_columns, metadata = read_csv(samples_path)
    required_columns = {"sample", "include", "genotype", "condition", "subject"}
    if missing := sorted(required_columns - set(metadata_columns)):
        raise ValueError("config/samples.csv is missing columns: " + ", ".join(missing))
    included = [row for row in metadata if parse_bool(row["include"])]
    if not included:
        raise ValueError("No samples are enabled.")
    names = [clean(row["sample"]) for row in included]
    if len(names) != len(set(names)):
        raise ValueError("Enabled sample names are duplicated.")
    if missing := sorted(set(names) - set(sheet_samples)):
        raise ValueError("Configured samples absent from samplesheet: " + ", ".join(missing))
    missing_quant = [name for name in names if not (salmon_dir / name / "quant.sf").is_file()]
    if missing_quant:
        raise ValueError("Missing Salmon quant.sf for: " + ", ".join(missing_quant))
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("analysis.yaml must be a mapping with schema_version: 1.")
    analysis = config.get("analysis") or {}
    require_keys(analysis, ("primary_contrast", "alpha", "lfc_threshold", "min_count", "min_samples", "top_labels", "top_heatmap"), "analysis")
    if not 0 < float(analysis["alpha"]) < 1:
        raise ValueError("analysis.alpha must be between 0 and 1.")
    contrasts = config.get("contrasts") or []
    ids = [clean(item.get("id")) for item in contrasts]
    if not ids or len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_]+", value) for value in ids):
        raise ValueError("Contrast ids must be non-empty, unique, and contain only letters, numbers, and underscores.")
    if clean(analysis["primary_contrast"]) not in ids:
        raise ValueError("analysis.primary_contrast must name a configured contrast.")
    groups = {clean(row["genotype"]) for row in included}
    conditions = {clean(row["condition"]) for row in included}
    subject_conditions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in included:
        require_keys(row, ("sample", "genotype", "condition", "subject"), "enabled sample")
        subject_conditions[(row["genotype"], row["subject"])].add(row["condition"])
    for contrast in contrasts:
        kind = clean(contrast.get("type"))
        if kind == "interaction":
            require_keys(contrast, ("base_group", "target_group", "base_condition", "target_condition"), contrast["id"])
            needed_groups = {contrast["base_group"], contrast["target_group"]}
            needed_conditions = {contrast["base_condition"], contrast["target_condition"]}
            if not needed_groups <= groups or not needed_conditions <= conditions:
                raise ValueError(f"Interaction {contrast['id']} refers to absent levels.")
            incomplete = [f"{group}:{subject}" for (group, subject), seen in subject_conditions.items() if group in needed_groups and not needed_conditions <= seen]
            if incomplete:
                raise ValueError(f"Interaction {contrast['id']} has incomplete pairs: {', '.join(incomplete)}")
        elif kind == "paired_condition":
            require_keys(contrast, ("group", "base_condition", "target_condition"), contrast["id"])
            needed = {contrast["base_condition"], contrast["target_condition"]}
            incomplete = [f"{group}:{subject}" for (group, subject), seen in subject_conditions.items() if group == contrast["group"] and not needed <= seen]
            if contrast["group"] not in groups or incomplete:
                raise ValueError(f"Paired contrast {contrast['id']} has absent levels or incomplete pairs: {', '.join(incomplete)}")
        elif kind == "two_group":
            require_keys(contrast, ("base_group", "target_group", "at_condition"), contrast["id"])
            if not {contrast["base_group"], contrast["target_group"]} <= groups or contrast["at_condition"] not in conditions:
                raise ValueError(f"Two-group contrast {contrast['id']} refers to absent levels.")
        else:
            raise ValueError(f"Unsupported contrast type for {contrast['id']}: {kind}")
    say(f"[green]Validation passed for {len(included)} samples and {len(contrasts)} contrasts.[/green]")


def main() -> int:
    args = parse_args()
    samplesheet = Path(args.samplesheet).expanduser().resolve()
    salmon_dir = Path(args.salmon_dir).expanduser().resolve()
    config_path = Path(args.config)
    samples_path = Path(args.samples_out)
    if args.configure:
        configure(samplesheet, config_path, samples_path, interactive=True)
    elif args.auto_if_missing:
        if not config_path.exists() or not samples_path.exists():
            configure(samplesheet, config_path, samples_path, interactive=False)
        else:
            say("Existing configuration preserved.")
    else:
        validate(samplesheet, salmon_dir, config_path, samples_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"[error] {exc}") from exc
