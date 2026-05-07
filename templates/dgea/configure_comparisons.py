#!/usr/bin/env python3
from __future__ import annotations

import argparse
import builtins
import csv
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from rich.console import Console
    from rich.markup import escape
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.syntax import Syntax
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    Console = None
    Confirm = None
    Panel = None
    Prompt = None
    Syntax = None
    Table = None
    escape = lambda text: text
    RICH_AVAILABLE = False


HIDDEN_COLUMNS = {"fastq_1", "fastq_2", "strandedness"}
BEGIN_METADATA = "# BEGIN CONFIGURED SAMPLE METADATA"
END_METADATA = "# END CONFIGURED SAMPLE METADATA"
BEGIN_COMPARISONS = "# BEGIN CONFIGURED COMPARISONS"
END_COMPARISONS = "# END CONFIGURED COMPARISONS"
NO_COLOR = os.environ.get("NO_COLOR") is not None
CONSOLE = Console(no_color=NO_COLOR, highlight=False) if RICH_AVAILABLE else None

if CONSOLE is not None:
    print = CONSOLE.print


def style(text: str, rich_style: str, ansi_code: str) -> str:
    if RICH_AVAILABLE:
        return f"[{rich_style}]{escape(text)}[/]"
    if NO_COLOR or not sys.stdout.isatty():
        return text
    return f"\033[{ansi_code}m{text}\033[0m"


def bold(text: str) -> str:
    return style(text, "bold", "1")


def dim(text: str) -> str:
    return style(text, "dim", "2")


def cyan(text: str) -> str:
    return style(text, "cyan", "36")


def green(text: str) -> str:
    return style(text, "green", "32")


def yellow(text: str) -> str:
    return style(text, "yellow", "33")


def magenta(text: str) -> str:
    return style(text, "magenta", "35")


def header(text: str) -> str:
    if RICH_AVAILABLE:
        return f"[bold cyan]{escape(text)}[/]"
    return bold(cyan(text))


def warning_text(text: str) -> str:
    return yellow(text)


def success_text(text: str) -> str:
    return green(text)


@dataclass
class Comparison:
    name: str
    base_group: str
    target_group: str
    design_formula: str
    subset_expr: str | None
    subset_label: str
    go: bool
    gsea: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactively write transparent DGEA comparisons into DGEA_constructor.R."
    )
    parser.add_argument("--samplesheet", required=True)
    parser.add_argument("--constructor", default="DGEA_constructor.R")
    return parser.parse_args()


def read_samplesheet(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames or []
    if "sample" not in columns:
        raise SystemExit("Samplesheet must contain a 'sample' column.")
    if not rows:
        raise SystemExit("Samplesheet is empty.")
    return columns, rows


def prompt(text: str, default: str | None = None) -> str:
    if Prompt is not None:
        value = Prompt.ask(text, default=default)
        return value.strip()
    suffix = dim(f" [{default}]") if default not in (None, "") else ""
    value = input(f"{bold(text)}{suffix}: ").strip()
    if value == "" and default is not None:
        return default
    return value


def prompt_bool(text: str, default: bool = True) -> bool:
    if Confirm is not None:
        return bool(Confirm.ask(text, default=default))
    marker = "Y/n" if default else "y/N"
    while True:
        value = input(f"{bold(text)} {dim(f'[{marker}]')}: ").strip().lower()
        if value == "":
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print(warning_text("Please answer y or n."))


def prompt_choice(text: str, choices: list[tuple[str, str]]) -> str:
    print(header(text))
    for key, label in choices:
        print(f"  {green(key)}. {label}")
    valid = {key for key, _ in choices}
    while True:
        if Prompt is not None:
            value = Prompt.ask("Selection", choices=sorted(valid), show_choices=False)
        else:
            value = input(f"{bold('Selection')}: ").strip()
        if value in valid:
            return value
        print(warning_text("Please choose one of: " + ", ".join(sorted(valid))))


def r_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def r_vector(values: Iterable[str]) -> str:
    return "c(" + ", ".join(r_string(value) for value in values) + ")"


def r_col_ref(name: str) -> str:
    if re.match(r"^[A-Za-z.][A-Za-z0-9_.]*$", name):
        return name
    return "`" + name.replace("`", "\\`") + "`"


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "comparison"


def visible_columns(columns: list[str]) -> list[str]:
    preferred = ["sample", "group", "genotype", "condition", "treatment", "id", "batch"]
    output = [col for col in preferred if col in columns and col not in HIDDEN_COLUMNS]
    output.extend(col for col in columns if col not in output and col not in HIDDEN_COLUMNS)
    return output


def print_table(rows: list[dict[str, str]], columns: list[str], title: str, limit: int = 30) -> None:
    if Table is not None and CONSOLE is not None:
        table = Table(title=title, title_style="bold cyan", header_style="bold", show_lines=False)
        table.add_column("idx", style="green", justify="right", no_wrap=True)
        for col in columns:
            table.add_column(col, overflow="fold")
        for idx, row in enumerate(rows[:limit], start=1):
            table.add_row(str(idx), *[str(row.get(col, "")) for col in columns])
        CONSOLE.print(table)
        if len(rows) > limit:
            CONSOLE.print(dim(f"... {len(rows) - limit} more samples"))
        if not rows:
            CONSOLE.print(dim("none"))
        return

    print(f"\n{header(title)}")
    if not rows:
        print(dim("  none"))
        return
    table_rows = rows[:limit]
    headers = ["idx", *columns]
    widths = {header: len(header) for header in headers}
    for idx, row in enumerate(table_rows, start=1):
        widths["idx"] = max(widths["idx"], len(str(idx)))
        for col in columns:
            widths[col] = max(widths[col], len(str(row.get(col, ""))))
    print("  " + "  ".join(bold(header.ljust(widths[header])) for header in headers))
    for idx, row in enumerate(table_rows, start=1):
        values = [str(idx), *[str(row.get(col, "")) for col in columns]]
        print("  " + "  ".join(value.ljust(widths[header]) for value, header in zip(values, headers)))
    if len(rows) > limit:
        print(dim(f"  ... {len(rows) - limit} more samples"))


def print_group_summary(rows: list[dict[str, str]]) -> None:
    if "group" not in rows[0]:
        return
    counts: dict[str, int] = {}
    for row in rows:
        group = row.get("group", "")
        if group:
            counts[group] = counts.get(group, 0) + 1
    if not counts:
        return
    if Table is not None and CONSOLE is not None:
        table = Table(title="Group summary", title_style="bold cyan", header_style="bold")
        table.add_column("group")
        table.add_column("n", justify="right", style="green")
        for group, count in sorted(counts.items()):
            table.add_row(group, str(count))
        CONSOLE.print(table)
        return

    print(f"\n{header('Group summary')}")
    width = max(len("group"), *(len(group) for group in counts))
    print("  " + bold("group".ljust(width)) + "  " + bold("n"))
    for group, count in sorted(counts.items()):
        print("  " + group.ljust(width) + f"  {count}")


def sample_parts(rows: list[dict[str, str]]) -> list[list[str]]:
    return [row["sample"].split("_") for row in rows]


def default_part_names(n_parts: int) -> list[str]:
    if n_parts == 2:
        return ["group", "id"]
    if n_parts == 3:
        return ["genotype", "condition", "id"]
    if n_parts == 4:
        return ["genotype", "condition", "treatment", "id"]
    names = [f"part{i}" for i in range(1, n_parts + 1)]
    names[-1] = "id"
    return names


def configure_metadata(columns: list[str], rows: list[dict[str, str]]) -> tuple[str, list[str], list[dict[str, str]]]:
    metadata_code = (
        "# No configured sample metadata. Edit this block or run ./run.sh --configure.\n"
        "# The constructor will use an existing 'group' column if present."
    )
    working_columns = list(columns)
    working_rows = [dict(row) for row in rows]

    split_parts = sample_parts(rows)
    part_counts = sorted({len(parts) for parts in split_parts})
    can_split = len(part_counts) == 1 and part_counts[0] > 1

    print(f"\n{header('Sample metadata')}")
    if "group" in columns:
        if not (can_split and prompt_bool("Derive or update metadata from sample names", default=False)):
            return metadata_code, working_columns, working_rows
    else:
        if not can_split:
            print(warning_text("No 'group' column was found, and sample names do not split cleanly by underscores."))
            print("Please add metadata columns manually before configuring pairwise comparisons.")
            return metadata_code, working_columns, working_rows
        print(warning_text("No 'group' column was found.") + " The configurator can derive metadata from sample names.")
        if not prompt_bool("Split sample names by underscore now", default=True):
            return metadata_code, working_columns, working_rows

    n_parts = part_counts[0]
    part_columns = [f"part{i}" for i in range(1, n_parts + 1)]
    preview = []
    for row, parts in zip(rows, split_parts):
        preview.append({"sample": row["sample"], **dict(zip(part_columns, parts))})
    print_table(preview, ["sample", *part_columns], "Detected sample-name parts", limit=12)

    names: list[str] = []
    used: set[str] = set()
    for idx, default in enumerate(default_part_names(n_parts), start=1):
        while True:
            if Prompt is not None:
                raw_name = Prompt.ask(f"Column name for part{idx} (- to skip)", default=default).strip()
            else:
                raw_name = input(
                    f"{bold(f'Column name for part{idx}')} {dim(f'[{default}; - to skip]')}: "
                ).strip()
            name = "" if raw_name == "-" else safe_name(raw_name or default)
            if name == "":
                names.append("")
                break
            if name in used:
                print(warning_text(f"Column name '{name}' is already used."))
                continue
            used.add(name)
            names.append(name)
            break

    usable_names = [name for name in names if name]
    if not usable_names:
        return metadata_code, working_columns, working_rows

    default_group_cols = [name for name in usable_names if name != "id"]
    if not default_group_cols:
        default_group_cols = [usable_names[0]]
    while True:
        group_input = prompt(
            "Columns that define group, comma-separated",
            ",".join(default_group_cols),
        )
        group_cols = [safe_name(value) for value in re.split(r"\s*,\s*", group_input) if value.strip()]
        unknown = [col for col in group_cols if col not in usable_names]
        if unknown:
            print(warning_text("Unknown parsed columns: " + ", ".join(unknown)))
            continue
        if not group_cols:
            print(warning_text("At least one group column is required."))
            continue
        break

    for row, parts in zip(working_rows, split_parts):
        for name, value in zip(names, parts):
            if name:
                row[name] = value
        row["group"] = "_".join(row[col] for col in group_cols)

    for name in usable_names + ["group"]:
        if name not in working_columns:
            working_columns.append(name)

    r_names = ["NA" if name == "" else r_string(name) for name in names]
    assign_lines = []
    for name in usable_names:
        assign_lines.append(f"samplesheet${name} <- sample_parts${name}")
    paste_args = ",\n  ".join(f"samplesheet${col}" for col in group_cols)
    metadata_code = "\n".join(
        [
            "# Generated by ./run.sh --configure. Edit freely if sample metadata changes.",
            "sample_parts <- tidyr::separate_wider_delim(",
            "  tibble(sample = samplesheet$sample),",
            "  sample,",
            '  delim = "_",',
            "  names = c(" + ", ".join(r_names) + "),",
            '  too_many = "merge",',
            '  too_few = "align_start"',
            ")",
            *assign_lines,
            "samplesheet$group <- paste(",
            f"  {paste_args},",
            '  sep = "_"',
            ")",
        ]
    )

    return metadata_code, working_columns, working_rows


def filter_rows(
    rows: list[dict[str, str]],
    columns: list[str],
) -> tuple[list[dict[str, str]], str | None, str]:
    choice = prompt_choice(
        "\nSample subset",
        [
            ("1", "Use all samples"),
            ("2", "Filter by column value"),
            ("3", "Select samples by index"),
            ("4", "Exclude samples by index"),
        ],
    )
    if choice == "1":
        return rows, None, "all samples"
    if choice == "2":
        filterable = [col for col in visible_columns(columns) if col != "sample"]
        if not filterable:
            print(warning_text("No metadata columns are available for filtering."))
            return rows, None, "all samples"
        column = prompt_choice(
            "Filter column",
            [(str(i), col) for i, col in enumerate(filterable, start=1)],
        )
        col = filterable[int(column) - 1]
        values = sorted({row.get(col, "") for row in rows})
        value_choice = prompt_choice(
            f"Value for {col}",
            [(str(i), value) for i, value in enumerate(values, start=1)],
        )
        value = values[int(value_choice) - 1]
        subset = [row for row in rows if row.get(col, "") == value]
        return subset, f"subset(samplesheet, {r_col_ref(col)} == {r_string(value)})", f"{col} == {value}"

    print_table(rows, visible_columns(columns), "Available samples for index selection")
    raw = prompt("Sample indexes, comma-separated")
    indexes = {int(value) for value in re.findall(r"\d+", raw)}
    selected = [row for idx, row in enumerate(rows, start=1) if idx in indexes]
    selected_samples = [row["sample"] for row in selected]
    if choice == "3":
        subset = selected
        expr = f"subset(samplesheet, sample %in% {r_vector(selected_samples)})"
        return subset, expr, "selected samples"
    excluded = selected_samples
    subset = [row for row in rows if row["sample"] not in excluded]
    expr = f"subset(samplesheet, !(sample %in% {r_vector(excluded)}))"
    return subset, expr, "excluded samples"


def validate_comparison(rows: list[dict[str, str]], base: str, target: str, formula: str) -> None:
    groups = [row.get("group", "") for row in rows]
    for group in [base, target]:
        n = groups.count(group)
        if n == 0:
            print(warning_text(f"Warning: group '{group}' has no samples in this subset."))
        elif n < 2:
            print(warning_text(f"Warning: group '{group}' has only {n} sample in this subset."))

    formula_cols = re.findall(r"[A-Za-z.][A-Za-z0-9_.]*", formula)
    formula_cols = [col for col in formula_cols if col not in {"group"}]
    available = set(rows[0].keys())
    missing = [col for col in formula_cols if col not in available]
    if missing:
        print(warning_text("Warning: formula columns not found in samplesheet: " + ", ".join(missing)))

    if "id" in formula_cols:
        by_id: dict[str, set[str]] = {}
        for row in rows:
            if row.get("group") in {base, target}:
                by_id.setdefault(row.get("id", ""), set()).add(row.get("group", ""))
        incomplete = [sample_id for sample_id, seen in by_id.items() if seen != {base, target}]
        if incomplete:
            print(warning_text("Warning: these ids do not have both base and target groups: " + ", ".join(incomplete)))
        else:
            print(success_text("Validation for formula with id: every id has both selected groups."))


def choose_formula(columns: list[str]) -> str:
    options = [("1", "~ group")]
    if "batch" in columns:
        options.append((str(len(options) + 1), "~ batch + group"))
    if "id" in columns:
        options.append((str(len(options) + 1), "~ id + group"))
    custom_key = str(len(options) + 1)
    options.append((custom_key, "Custom formula"))
    choice = prompt_choice("\nDesign formula", options)
    if choice == custom_key:
        return prompt("Custom formula", "~ group")
    return dict(options)[choice]


def comparison_to_r(comparison: Comparison, indent: str = "  ") -> str:
    lines = [indent + "list("]
    lines.append(indent + f"  name = {r_string(comparison.name)},")
    if comparison.subset_expr:
        lines.append(indent + f"  samplesheet = {comparison.subset_expr},")
    lines.extend(
        [
            indent + f"  base_group = {r_string(comparison.base_group)},",
            indent + f"  target_group = {r_string(comparison.target_group)},",
            indent + f"  design_formula = {r_string(comparison.design_formula)},",
            indent + f"  go = {str(comparison.go).upper()},",
            indent + f"  gsea = {str(comparison.gsea).upper()}",
            indent + ")",
        ]
    )
    return "\n".join(lines)


def add_comparison(rows: list[dict[str, str]], columns: list[str]) -> Comparison | None:
    subset_rows, subset_expr, subset_label = filter_rows(rows, columns)
    if not subset_rows:
        print(warning_text("No samples selected."))
        return None
    print_table(subset_rows, visible_columns(columns), "Selected samples")
    print_group_summary(subset_rows)
    groups = sorted({row.get("group", "") for row in subset_rows if row.get("group", "")})
    if len(groups) < 2:
        print(warning_text("At least two groups are required for a comparison."))
        return None
    base = prompt_choice("Base group", [(str(i), group) for i, group in enumerate(groups, start=1)])
    target = prompt_choice("Target group", [(str(i), group) for i, group in enumerate(groups, start=1)])
    base_group = groups[int(base) - 1]
    target_group = groups[int(target) - 1]
    if base_group == target_group:
        print(warning_text("Base and target group must be different."))
        return None
    default_name = safe_name(f"{target_group}_vs_{base_group}")
    name = safe_name(prompt("Comparison name", default_name))
    formula = choose_formula(columns)
    go = prompt_bool("GO enrichment", default=True)
    gsea = prompt_bool("GSEA", default=True)
    validate_comparison(subset_rows, base_group, target_group, formula)
    comparison = Comparison(
        name=name,
        base_group=base_group,
        target_group=target_group,
        design_formula=formula,
        subset_expr=subset_expr,
        subset_label=subset_label,
        go=go,
        gsea=gsea,
    )
    code = comparison_to_r(comparison, indent="")
    if Syntax is not None and CONSOLE is not None:
        CONSOLE.print(Panel(Syntax(code, "r", theme="ansi_dark"), title="Preview R code", border_style="magenta"))
    else:
        print(f"\n{header('Preview R code')}\n")
        print(magenta(code))
    if prompt_bool("Add this comparison", default=True):
        return comparison
    return None


def review_comparisons(comparisons: list[Comparison]) -> None:
    if Table is not None and CONSOLE is not None:
        table = Table(title="Configured comparisons", title_style="bold cyan", header_style="bold")
        table.add_column("#", justify="right", style="green", no_wrap=True)
        table.add_column("name", style="bold")
        table.add_column("samples")
        table.add_column("contrast")
        table.add_column("formula", style="magenta")
        table.add_column("GO", justify="center")
        table.add_column("GSEA", justify="center")
        if comparisons:
            for idx, comparison in enumerate(comparisons, start=1):
                table.add_row(
                    str(idx),
                    comparison.name,
                    comparison.subset_label,
                    f"{comparison.target_group} vs {comparison.base_group}",
                    comparison.design_formula,
                    str(comparison.go).upper(),
                    str(comparison.gsea).upper(),
                )
        else:
            table.add_row("-", "none", "", "", "", "", "")
        CONSOLE.print(table)
        return

    print(f"\n{header('Configured comparisons')}")
    if not comparisons:
        print(dim("  none"))
        return
    for idx, comparison in enumerate(comparisons, start=1):
        print(f"  {green(str(idx))}. {bold(comparison.name)}")
        print(f"     samples: {comparison.subset_label}")
        print(f"     contrast: {cyan(comparison.target_group)} vs {cyan(comparison.base_group)}")
        print(f"     formula: {magenta(comparison.design_formula)}")
        print(f"     GO: {str(comparison.go).upper()}; GSEA: {str(comparison.gsea).upper()}")


def replace_block(text: str, begin: str, end: str, body: str) -> str:
    pattern = re.compile(rf"{re.escape(begin)}\n.*?\n{re.escape(end)}", re.DOTALL)
    replacement = f"{begin}\n{body.rstrip()}\n{end}"
    if not pattern.search(text):
        raise SystemExit(f"Could not find configured block markers: {begin} / {end}")
    return pattern.sub(replacement, text, count=1)


def write_constructor(path: Path, metadata_code: str, comparisons: list[Comparison]) -> None:
    text = path.read_text(encoding="utf-8")
    comparison_body = "comparisons <- list()"
    if comparisons:
        rendered = ",\n".join(comparison_to_r(comparison, indent="  ") for comparison in comparisons)
        comparison_body = "comparisons <- list(\n" + rendered + "\n)"
    text = replace_block(text, BEGIN_METADATA, END_METADATA, metadata_code)
    text = replace_block(text, BEGIN_COMPARISONS, END_COMPARISONS, comparison_body)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if not sys.stdin.isatty():
        raise SystemExit("Interactive configuration requires a terminal.")

    args = parse_args()
    samplesheet_path = Path(args.samplesheet).resolve()
    constructor_path = Path(args.constructor).resolve()
    columns, rows = read_samplesheet(samplesheet_path)

    if Panel is not None and CONSOLE is not None:
        CONSOLE.print(Panel.fit("DGEA comparison configurator", style="bold cyan"))
    else:
        print(header("DGEA comparison configurator"))
    print(f"\n{bold('Samplesheet')}:\n  {samplesheet_path}")
    hidden = [col for col in columns if col in HIDDEN_COLUMNS]
    if hidden:
        print(f"\n{dim('Hidden sequencing input columns')}:\n  " + dim(", ".join(hidden)))
    print_table(rows, visible_columns(columns), "Detected samples")

    metadata_code, working_columns, working_rows = configure_metadata(columns, rows)
    print_table(working_rows, visible_columns(working_columns), "Analysis samples")
    print_group_summary(working_rows)

    comparisons: list[Comparison] = []
    while True:
        review_comparisons(comparisons)
        choice = prompt_choice(
            "\nChoose action",
            [
                ("1", "Add comparison"),
                ("2", "Remove comparison"),
                ("3", "Finish and write DGEA_constructor.R"),
                ("4", "Exit without writing"),
            ],
        )
        if choice == "1":
            comparison = add_comparison(working_rows, working_columns)
            if comparison is not None:
                comparisons.append(comparison)
        elif choice == "2":
            if not comparisons:
                print(warning_text("No comparisons to remove."))
                continue
            idx = int(prompt_choice("Remove comparison", [(str(i), c.name) for i, c in enumerate(comparisons, start=1)]))
            comparisons.pop(idx - 1)
        elif choice == "3":
            write_constructor(constructor_path, metadata_code, comparisons)
            print(success_text(f"\nUpdated {constructor_path}"))
            print("Inspect DGEA_constructor.R, then run ./run.sh when ready.")
            return 0
        elif choice == "4":
            print(warning_text("No changes written."))
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
