#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
from pathlib import Path
from urllib.request import Request, urlopen


SC_TYPE_DB_URL = "https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/ScTypeDB_full.xlsx"
SC_TYPE_CITATION = (
    "ScType marker database; Ianevski et al. Nat Commun. 2022; "
    "https://github.com/IanevskiAleksandr/sc-type"
)
CATALOG_FIELDS = [
    "catalog_id",
    "species",
    "organism_id",
    "tissue",
    "cell_type",
    "gene_symbol",
    "marker_role",
    "source",
    "citation",
    "evidence",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and convert ScType marker catalogs.")
    parser.add_argument("catalog", choices=["sctype"], help="Catalog source to download and convert.")
    parser.add_argument(
        "--cache-dir",
        default=default_cache_dir(),
        help="Catalog cache directory. Defaults to SCRNA_ANNOTATE_CATALOG_CACHE, SCRNA_ANNOTATE_CACHE_DIR, or ~/.cache/izkf_pack/scrna_annotate_sctype/catalogs.",
    )
    parser.add_argument("--refresh", action="store_true", help="Re-download and re-convert even when cached files exist.")
    args = parser.parse_args()

    path = ensure_catalog(args.catalog, Path(args.cache_dir).expanduser(), refresh=args.refresh)
    print(path)
    return 0


def ensure_catalog(catalog: str, cache_dir: Path, *, refresh: bool = False) -> Path:
    if catalog != "sctype":
        raise SystemExit(f"Unsupported catalog: {catalog}")
    return ensure_sctype_catalog(cache_dir, refresh=refresh)


def ensure_sctype_catalog(cache_dir: Path, *, refresh: bool = False) -> Path:
    source_dir = cache_dir / "sctype"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / "ScTypeDB_full.xlsx"
    catalog_path = source_dir / "marker_catalog.tsv"
    metadata_path = source_dir / "metadata.txt"

    if refresh or not raw_path.exists():
        download(SC_TYPE_DB_URL, raw_path)
    if refresh or not catalog_path.exists():
        convert_sctype(raw_path, catalog_path)
    metadata_path.write_text(
        "\n".join(
            [
                "source=sctype",
                f"url={SC_TYPE_DB_URL}",
                f"raw_path={raw_path}",
                f"raw_sha256={sha256_file(raw_path)}",
                f"catalog_path={catalog_path}",
                f"catalog_sha256={sha256_file(catalog_path)}",
            ]
        )
        + "\n"
    )
    return catalog_path


def convert_sctype(raw_path: Path, catalog_path: Path) -> None:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("pandas is required to convert ScTypeDB_full.xlsx") from exc

    df = pd.read_excel(raw_path)
    required = {"tissueType", "cellName", "geneSymbolmore1", "geneSymbolmore2"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"ScType database is missing columns: {', '.join(sorted(missing))}")

    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for _, row in df.iterrows():
        tissue = clean_text(row.get("tissueType"))
        cell_type = clean_text(row.get("cellName"))
        short_name = clean_text(row.get("shortName"))
        if not cell_type:
            continue
        for role, column in [("positive", "geneSymbolmore1"), ("negative", "geneSymbolmore2")]:
            for gene in split_gene_symbols(row.get(column)):
                for species, organism_id, converted_gene in species_gene_variants(gene):
                    key = (species, tissue.lower(), cell_type.lower(), role, converted_gene.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        {
                            "catalog_id": "sctype",
                            "species": species,
                            "organism_id": organism_id,
                            "tissue": tissue,
                            "cell_type": cell_type,
                            "gene_symbol": converted_gene,
                            "marker_role": role,
                            "source": "ScType marker database",
                            "citation": SC_TYPE_CITATION,
                            "evidence": f"shortName={short_name}; source_column={column}",
                        }
                    )

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    with catalog_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOG_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def species_gene_variants(gene: str) -> list[tuple[str, str, str]]:
    human_gene = gene.strip().upper()
    if not human_gene:
        return []
    mouse_gene = human_gene[0] + human_gene[1:].lower()
    return [
        ("human", "NCBITaxon:9606", human_gene),
        ("mouse", "NCBITaxon:10090", mouse_gene),
    ]


def split_gene_symbols(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    genes = []
    for item in str(value).replace(";", ",").split(","):
        gene = clean_text(item)
        if gene and gene.lower() != "nan":
            genes.append(gene)
    return genes


def clean_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def download(url: str, path: Path) -> None:
    request = Request(url, headers={"User-Agent": "izkf_pack scrna_annotate_sctype"})
    with urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())


def default_cache_dir() -> str:
    return os.environ.get(
        "SCRNA_ANNOTATE_CATALOG_CACHE",
        os.environ.get("SCRNA_ANNOTATE_CACHE_DIR", "~/.cache/izkf_pack/scrna_annotate_sctype/catalogs"),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
