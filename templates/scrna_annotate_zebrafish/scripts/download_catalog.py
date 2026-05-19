#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import os
from pathlib import Path
from urllib.request import Request, urlopen


CATALOG_FIELDS = [
    "catalog_id",
    "species",
    "organism_id",
    "tissue",
    "stage",
    "cell_type",
    "gene_symbol",
    "source",
    "citation",
    "evidence",
]
ZCL_2_MARKER_LIST_URL = "https://bis.zju.edu.cn/ZCL/data/zclmarkerlist.csv"
ZCL_2_CITATION = (
    "Zebrafish Cell Landscape 2.0 marker list; "
    "Jiang et al. Front Cell Dev Biol. 2021; Wang et al. Nucleic Acids Res. 2022; "
    "https://bis.zju.edu.cn/ZCL/"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and convert zebrafish marker catalogs.")
    parser.add_argument(
        "catalog",
        choices=["zcl_2_marker_list"],
        help="Catalog source to download and convert.",
    )
    parser.add_argument(
        "--cache-dir",
        default=default_cache_dir(),
        help="Catalog cache directory. Defaults to SCRNA_ANNOTATE_CATALOG_CACHE, SCRNA_ANNOTATE_CACHE_DIR, or ~/.cache/izkf_pack/scrna_annotate_zebrafish/catalogs.",
    )
    parser.add_argument("--refresh", action="store_true", help="Re-download and re-convert even when cached files exist.")
    args = parser.parse_args()

    path = ensure_catalog(args.catalog, Path(args.cache_dir).expanduser(), refresh=args.refresh)
    print(path)
    return 0


def ensure_catalog(catalog: str, cache_dir: Path, *, refresh: bool = False) -> Path:
    if catalog != "zcl_2_marker_list":
        raise SystemExit(f"Unsupported catalog: {catalog}")
    return ensure_zcl_2_marker_list(cache_dir, refresh=refresh)


def ensure_zcl_2_marker_list(cache_dir: Path, *, refresh: bool = False) -> Path:
    source_dir = cache_dir / "zcl_2_marker_list"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / "zclmarkerlist.csv"
    catalog_path = source_dir / "marker_catalog.tsv"
    metadata_path = source_dir / "metadata.txt"

    if refresh or not raw_path.exists():
        download(ZCL_2_MARKER_LIST_URL, raw_path)
    if refresh or not catalog_path.exists():
        convert_zcl_2_marker_list(raw_path, catalog_path)
    metadata_path.write_text(
        "\n".join(
            [
                "source=zcl_2_marker_list",
                f"url={ZCL_2_MARKER_LIST_URL}",
                f"raw_path={raw_path}",
                f"raw_sha256={sha256_file(raw_path)}",
                f"catalog_path={catalog_path}",
                f"catalog_sha256={sha256_file(catalog_path)}",
            ]
        )
        + "\n"
    )
    return catalog_path


def convert_zcl_2_marker_list(raw_path: Path, catalog_path: Path) -> None:
    seen: set[tuple[str, str, str]] = set()
    rows: list[dict[str, str]] = []
    with raw_path.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle)
        required = {"Cluster", "Cell-type", "Gene", "P-val", "Scores"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"ZCL marker list is missing columns: {', '.join(sorted(missing))}")
        for raw in reader:
            cell_type = clean_text(raw.get("Cell-type"))
            gene_symbol = clean_text(raw.get("Gene"))
            cluster = clean_text(raw.get("Cluster"))
            if not cell_type or not gene_symbol:
                continue
            key = (cell_type.lower(), gene_symbol.lower(), cluster)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "catalog_id": "zcl_2_marker_list",
                    "species": "zebrafish",
                    "organism_id": "NCBITaxon:7955",
                    "tissue": "whole fish / multi-tissue",
                    "stage": "ZCL2 mixed stages; includes 72 hpf",
                    "cell_type": cell_type,
                    "gene_symbol": gene_symbol,
                    "source": "ZCL 2.0 marker list",
                    "citation": ZCL_2_CITATION,
                    "evidence": f"cluster={cluster}; pval={clean_text(raw.get('P-val'))}; score={clean_text(raw.get('Scores'))}",
                }
            )
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    with catalog_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOG_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def clean_text(value: object) -> str:
    return str(value or "").strip()


def download(url: str, path: Path) -> None:
    request = Request(url, headers={"User-Agent": "izkf_pack scrna_annotate_zebrafish"})
    with urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())


def default_cache_dir() -> str:
    return os.environ.get(
        "SCRNA_ANNOTATE_CATALOG_CACHE",
        os.environ.get("SCRNA_ANNOTATE_CACHE_DIR", "~/.cache/izkf_pack/scrna_annotate_zebrafish/catalogs"),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
