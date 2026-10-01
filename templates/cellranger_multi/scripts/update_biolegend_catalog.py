#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import re
from pathlib import Path
from urllib.request import Request, urlopen


BASE_URL = "https://fo-biolegend-sbx1.mydwsite.com/en-us/totalseq/barcode-lookup"
ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
INPUT_RE = re.compile(r"<input\s+([^>]+)>", re.DOTALL | re.IGNORECASE)
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
FIELDS = [
    "catalog_id",
    "vendor",
    "product_family",
    "species",
    "catalog_number",
    "barcode_id",
    "target",
    "clone",
    "application",
    "gene_ids",
    "rrid",
    "released",
    "source_url",
]


def clean(value: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub("", value)).split())


def cellranger_label(value: str) -> str:
    return re.sub(r'[\s/,\"]+', ".", value).strip(".")


def download(url: str) -> str:
    request = Request(url, headers={"User-Agent": "izkf_pack feature-catalog maintainer"})
    with urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_rows(page: str, *, family: str, species: str, application: str, source_url: str) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row_html in ROW_RE.findall(page):
        input_match = INPUT_RE.search(row_html)
        if input_match is None:
            continue
        attrs = dict(ATTR_RE.findall(input_match.group(1)))
        data_cr = html.unescape(attrs.get("data-cr", ""))
        raw_value = html.unescape(attrs.get("value", ""))
        cr_parts = data_cr.split("|")
        value_parts = raw_value.split("|")
        cells = [clean(cell) for cell in TD_RE.findall(row_html)]
        if len(cr_parts) != 6 or len(value_parts) < 7 or len(cells) < 9:
            continue
        reactivity = cells[5]
        if species.lower() not in {item.strip().lower() for item in reactivity.split(",")}:
            if clean(value_parts[4]).lower() != "isotype":
                continue
        feature_type = "Antibody Capture" if application == "hashing" else cr_parts[5]
        selected.append(
            {
                "catalog_id": f"biolegend_totalseq_{family.lower()}_{species.lower()}" + ("_hashing" if application == "hashing" else ""),
                "vendor": "BioLegend",
                "product_family": f"TotalSeq-{family}",
                "species": species,
                "catalog_number": value_parts[0],
                "barcode_id": value_parts[1],
                "target": value_parts[4],
                "clone": value_parts[5],
                "sequence": cr_parts[4],
                "read": cr_parts[2],
                "pattern": cr_parts[3],
                "feature_type": feature_type,
                "application": application,
                "gene_ids": value_parts[3],
                "rrid": value_parts[6],
                "released": cells[8],
                "source_url": source_url,
                "id": cellranger_label(cr_parts[0]),
                "name": cellranger_label(cr_parts[1]),
            }
        )
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a versioned BioLegend TotalSeq catalog snapshot.")
    parser.add_argument("--family", choices=["A", "B", "C"], required=True)
    parser.add_argument("--species", choices=["Human", "Mouse"], required=True)
    parser.add_argument("--application", choices=["surface_protein", "hashing"], default="surface_protein")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    suffix = f"totalseq-{args.family.lower()}-" + ("hashtags" if args.application == "hashing" else "antibodies")
    url = f"{BASE_URL}/{suffix}?LayoutTemplate=Designs/BioLegend/jsonRetriever.cshtml"
    rows = parse_rows(download(url), family=args.family, species=args.species, application=args.application, source_url=url)
    if not rows:
        raise SystemExit(f"No rows were parsed from {url}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output_fields = ["id", "name", "read", "pattern", "sequence", "feature_type", *FIELDS]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
