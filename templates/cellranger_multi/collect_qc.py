#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path
from urllib.parse import quote


SAMPLE_QC_NAME = "sample_qc_overview.csv"
LIBRARY_QC_NAME = "gem_well_library_qc.csv"
HASHTAG_QC_NAME = "hashtag_assignment_overview.csv"
REPORT_NAME = "qc_overview.html"

SAMPLE_COLUMNS = [
    "GEM well",
    "Sample ID",
    "Sample barcodes",
    "GEX: Cells",
    "GEX: Number of reads in cells",
    "GEX: Reads in cells per cell",
    "GEX: Median genes per cell",
    "GEX: Median UMI counts per cell",
    "GEX: Confidently mapped to transcriptome",
    "Antibody: Number of reads in cells",
    "Antibody: Reads in cells per cell",
    "GEM-well GEX mean reads per cell",
    "GEM-well GEX sequencing saturation",
]

DEPTH_COLUMNS = [
    "GEX: Reads in cells per cell",
    "Antibody: Reads in cells per cell",
    "GEM-well GEX total reads",
    "GEM-well GEX mean reads per cell",
    "GEM-well GEX sequencing saturation",
]

DISPLAY_LABELS = {
    "Sample ID": "Sample",
    "Sample barcodes": "Hashtag",
    "GEX: Cells": "Cells",
    "GEX: Number of reads in cells": "GEX reads",
    "GEX: Reads in cells per cell": "GEX reads/cell",
    "GEX: Median genes per cell": "Median genes/cell",
    "GEX: Median UMI counts per cell": "Median UMIs/cell",
    "GEX: Confidently mapped to transcriptome": "Mapped to transcriptome",
    "Antibody: Number of reads in cells": "Hashtag reads",
    "Antibody: Reads in cells per cell": "Hashtag reads/cell",
    "GEM-well GEX mean reads per cell": "GEM-well reads/cell",
    "GEM-well GEX sequencing saturation": "GEX saturation",
    "Cell-associated barcodes": "Cell barcodes",
    "Singlet assigned cells": "Singlets",
    "Singlet assigned %": "Singlet %",
    "Multiplet cells": "Multiplets",
    "Unassigned cells": "Unassigned",
    "No tag molecules cells": "No-tag cells",
    "No tag molecules %": "No-tag %",
}

HASHTAG_CATEGORIES = {
    "No tag molecules": "No tag molecules",
    "No tag assigned": "Unassigned",
    "1 tag assigned": "Singlet assigned",
    "More than 1 tag assigned": "Multiplet",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Cell Ranger multi QC CSV files into cross-sample overview tables and HTML."
    )
    parser.add_argument("--results-dir", required=True, help="Cell Ranger multi results directory.")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Defaults to <results-dir>/qc.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = [str(field) for field in (reader.fieldnames or []) if field]
        rows = [
            {str(key): str(value or "") for key, value in row.items() if key is not None}
            for row in reader
        ]
    return fields, rows


def ordered_union(preferred: list[str], field_groups: list[list[str]]) -> list[str]:
    fields: list[str] = []
    for field in preferred:
        if field not in fields:
            fields.append(field)
    for group in field_groups:
        for field in group:
            if field and field not in fields:
                fields.append(field)
    return fields


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect_prefixed_csvs(
    paths: list[Path],
) -> tuple[list[str], list[dict[str, str]]]:
    field_groups: list[list[str]] = []
    output_rows: list[dict[str, str]] = []
    for path in paths:
        fields, rows = read_csv(path)
        field_groups.append(fields)
        gem_well = path.parents[1].name
        for row in rows:
            output_rows.append({"GEM well": gem_well, **row})
    return ordered_union(["GEM well"], field_groups), output_rows


def number(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def integer_text(value: float | None) -> str:
    if value is None:
        return ""
    return str(int(round(value)))


def percent_text(value: str) -> str:
    numeric = number(value)
    if numeric is None:
        return str(value)
    if 0 <= numeric <= 1:
        numeric *= 100
    return f"{numeric:.1f}"


def collect_hashtag_qc(paths: list[Path]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for path in paths:
        _, rows = read_csv(path)
        by_category = {row.get("Category", ""): row for row in rows}
        summary: dict[str, str] = {"GEM well": path.parents[2].name}
        for source_name, output_name in HASHTAG_CATEGORIES.items():
            source = by_category.get(source_name, {})
            summary[f"{output_name} cells"] = str(source.get("num_cells", ""))
            summary[f"{output_name} %"] = percent_text(str(source.get("pct_cells", "")))

        unassigned = number(summary.get("Unassigned cells", ""))
        singlets = number(summary.get("Singlet assigned cells", ""))
        multiplets = number(summary.get("Multiplet cells", ""))
        values = [value for value in (unassigned, singlets, multiplets) if value is not None]
        summary["Cell-associated barcodes"] = integer_text(sum(values)) if len(values) == 3 else ""
        output.append(summary)
    return output


def enrich_sample_depth(
    sample_fields: list[str],
    sample_rows: list[dict[str, str]],
    library_rows: list[dict[str, str]],
) -> list[str]:
    """Add sample-assigned and pooled GEM-well sequencing-depth metrics."""
    metric_columns = {
        "Number of reads": "GEM-well GEX total reads",
        "Number of reads in the library": "GEM-well GEX total reads",
        "Mean reads per cell": "GEM-well GEX mean reads per cell",
        "Sequencing saturation": "GEM-well GEX sequencing saturation",
    }
    gem_metrics: dict[str, dict[str, str]] = {}
    for row in library_rows:
        if row.get("Library Type", "").strip() != "Gene Expression":
            continue
        if row.get("Grouped By", "").strip() != "Physical library ID":
            continue
        metric_name = row.get("Metric Name", "").strip()
        output_column = metric_columns.get(metric_name)
        value = row.get("Metric Value", "").strip()
        if not output_column or not value:
            continue
        values = gem_metrics.setdefault(row.get("GEM well", ""), {})
        # Prefer Cell Ranger's explicit "in the library" total when both names exist.
        if output_column not in values or metric_name == "Number of reads in the library":
            values[output_column] = value

    for row in sample_rows:
        cells = number(row.get("GEX: Cells", ""))
        gex_reads = number(row.get("GEX: Number of reads in cells", ""))
        antibody_reads = number(row.get("Antibody: Number of reads in cells", ""))
        if cells and gex_reads is not None:
            row["GEX: Reads in cells per cell"] = integer_text(gex_reads / cells)
        if cells and antibody_reads is not None:
            row["Antibody: Reads in cells per cell"] = integer_text(antibody_reads / cells)
        row.update(gem_metrics.get(row.get("GEM well", ""), {}))

    return ordered_union(sample_fields, [DEPTH_COLUMNS])


def display_value(column: str, value: str) -> str:
    value = str(value or "").strip()
    numeric = number(value)
    if numeric is None:
        return value or "—"
    lower = column.lower()
    if lower.endswith(" %"):
        return f"{numeric:.1f}%"
    if any(token in lower for token in ("fraction", "confidently mapped", "mapped to", "saturation")) and 0 <= numeric <= 1:
        return f"{numeric * 100:.1f}%"
    if numeric.is_integer():
        return f"{int(numeric):,}"
    return f"{numeric:,.2f}"


def render_table(
    rows: list[dict[str, str]],
    columns: list[str],
    *,
    link_column: str = "",
) -> str:
    if not rows:
        return '<p class="empty">No matching Cell Ranger output was found.</p>'
    available = [column for column in columns if any(str(row.get(column, "")).strip() for row in rows)]
    parts = ['<div class="table-wrap"><table><thead><tr>']
    parts.extend(
        f'<th title="{html.escape(column, quote=True)}">'
        f"{html.escape(DISPLAY_LABELS.get(column, column))}</th>"
        for column in available
    )
    if link_column:
        parts.append('<th title="Original Cell Ranger web summary">Report</th>')
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        for column in available:
            parts.append(f"<td>{html.escape(display_value(column, row.get(column, '')))}</td>")
        if link_column:
            gem_well = quote(row.get("GEM well", ""), safe="")
            sample_id = quote(row.get("Sample ID", ""), safe="")
            href = f"../{gem_well}/outs/per_sample_outs/{sample_id}/web_summary.html"
            parts.append(f'<td><a href="{href}">Open summary</a></td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def build_html(
    sample_rows: list[dict[str, str]],
    hashtag_rows: list[dict[str, str]],
    gem_wells: list[str],
) -> str:
    total_cells = sum(number(row.get("GEX: Cells", "")) or 0 for row in sample_rows)
    hashtag_columns = [
        "GEM well",
        "Cell-associated barcodes",
        "Singlet assigned cells",
        "Singlet assigned %",
        "Multiplet cells",
        "Multiplet %",
        "Unassigned cells",
        "Unassigned %",
        "No tag molecules cells",
        "No tag molecules %",
    ]
    sample_table = render_table(sample_rows, SAMPLE_COLUMNS, link_column="Sample ID")
    hashtag_table = render_table(hashtag_rows, hashtag_columns)
    gem_links = "".join(
        f'<li><a href="../{quote(gem, safe="")}/outs/qc_report.html">{html.escape(gem)} GEM-well QC</a></li>'
        for gem in gem_wells
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cell Ranger multi QC overview</title>
  <style>
    :root {{ color-scheme: light; --ink:#18212b; --muted:#596775; --line:#d8e0e7; --accent:#176b87; --soft:#edf6f8; }}
    body {{ margin:0; font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#f7f9fb; }}
    main {{ max-width:1400px; margin:0 auto; padding:2rem; }}
    h1 {{ margin-bottom:.35rem; }} h2 {{ margin-top:2.2rem; }}
    p, li {{ line-height:1.55; }} .muted, .empty {{ color:var(--muted); }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:1rem; margin:1.5rem 0; }}
    .card {{ background:white; border:1px solid var(--line); border-radius:10px; padding:1rem 1.2rem; }}
    .card strong {{ display:block; font-size:1.7rem; color:var(--accent); }}
    .downloads a {{ display:inline-block; margin:.25rem .75rem .25rem 0; }}
    .table-wrap {{ overflow-x:auto; background:white; border:1px solid var(--line); border-radius:10px; }}
    table {{ border-collapse:collapse; width:100%; font-size:.9rem; }}
    th, td {{ padding:.65rem .75rem; border-bottom:1px solid var(--line); text-align:right; }}
    td {{ white-space:nowrap; }}
    th {{ background:var(--soft); position:sticky; top:0; white-space:normal; line-height:1.25; max-width:9rem; }}
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align:left; }}
    tr:last-child td {{ border-bottom:0; }} a {{ color:var(--accent); }}
    .note {{ border-left:4px solid var(--accent); background:var(--soft); padding:.8rem 1rem; }}
  </style>
</head>
<body><main>
  <h1>Cell Ranger multi QC overview</h1>
  <p class="muted">Automatically consolidated from final Cell Ranger CSV outputs. Values are descriptive and are not automatic pass/fail calls.</p>
  <div class="cards">
    <div class="card"><strong>{len(gem_wells)}</strong>GEM wells</div>
    <div class="card"><strong>{len(sample_rows)}</strong>biological samples</div>
    <div class="card"><strong>{int(total_cells):,}</strong>assigned sample cells</div>
  </div>
  <p class="downloads"><strong>Download tables:</strong>
    <a href="{SAMPLE_QC_NAME}">Sample QC CSV</a>
    <a href="{LIBRARY_QC_NAME}">GEM-well/library metrics CSV</a>
    <a href="{HASHTAG_QC_NAME}">Hashtag assignment CSV</a>
  </p>
  <h2>Biological-sample QC</h2>
  {sample_table}
  <p class="note"><strong>Depth definitions:</strong> “Number of reads in cells” is the total number of reads assigned to called cells in each hashtag-defined biological sample; “reads in cells per cell” divides that value by the sample's GEX cell count. GEM-well GEX depth and saturation describe the complete pooled Gene Expression library and therefore repeat for samples from the same GEM well. They are not independent raw sequencing depths for each hashed sample.</p>
  <p class="note">For antibody-based hashing experiments, the Antibody Capture values describe hashtag signal. They must not be interpreted as surface-protein expression measurements.</p>
  <h2>Hashtag assignment by GEM well</h2>
  {hashtag_table}
  <p class="muted">“No tag molecules” is a subset of unassigned cell-associated barcodes and is therefore not added again to the total.</p>
  <h2>Original GEM-well reports</h2>
  <ul>{gem_links}</ul>
  <h2>Interpretation boundary</h2>
  <p>This report summarizes Cell Ranger primary-analysis metrics. Cell-level mitochondrial fraction, genes/UMIs distributions, ambient RNA assessment, and downstream doublet scoring should be evaluated in the downstream single-cell QC workflow.</p>
</main></body></html>
"""


def collect_qc(results_dir: Path, output_dir: Path | None = None) -> dict[str, object]:
    results_dir = results_dir.expanduser().resolve()
    output_dir = (output_dir or (results_dir / "qc")).expanduser().resolve()
    sample_paths = sorted(results_dir.glob("*/outs/qc_sample_metrics.csv"))
    library_paths = sorted(results_dir.glob("*/outs/qc_library_metrics.csv"))
    hashtag_paths = sorted(results_dir.glob("*/outs/multiplexing_analysis/tag_calls_summary.csv"))
    if not sample_paths and not library_paths:
        raise SystemExit(f"[error] no final Cell Ranger QC CSV files found under {results_dir}")

    sample_fields, sample_rows = collect_prefixed_csvs(sample_paths)
    library_fields, library_rows = collect_prefixed_csvs(library_paths)
    sample_fields = enrich_sample_depth(sample_fields, sample_rows, library_rows)
    hashtag_rows = collect_hashtag_qc(hashtag_paths)
    hashtag_fields = [
        "GEM well",
        "Cell-associated barcodes",
        "Singlet assigned cells",
        "Singlet assigned %",
        "Multiplet cells",
        "Multiplet %",
        "Unassigned cells",
        "Unassigned %",
        "No tag molecules cells",
        "No tag molecules %",
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / SAMPLE_QC_NAME, sample_fields, sample_rows)
    write_csv(output_dir / LIBRARY_QC_NAME, library_fields, library_rows)
    write_csv(output_dir / HASHTAG_QC_NAME, hashtag_fields, hashtag_rows)
    gem_wells = sorted({path.parents[1].name for path in sample_paths + library_paths})
    (output_dir / REPORT_NAME).write_text(
        build_html(sample_rows, hashtag_rows, gem_wells), encoding="utf-8"
    )
    return {
        "gem_wells": len(gem_wells),
        "samples": len(sample_rows),
        "sample_rows": len(sample_rows),
        "library_metric_rows": len(library_rows),
        "hashtag_gem_wells": len(hashtag_rows),
        "output_dir": str(output_dir),
    }


def main() -> int:
    args = parse_args()
    payload = collect_qc(
        Path(args.results_dir),
        Path(args.output_dir) if args.output_dir.strip() else None,
    )
    print(
        "[info] wrote Cell Ranger QC overview for "
        f"{payload['samples']} biological sample(s) across {payload['gem_wells']} GEM well(s) "
        f"to {payload['output_dir']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
