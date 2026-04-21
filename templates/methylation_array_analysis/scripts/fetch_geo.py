#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from registry_common import load_registry, save_registry, upsert_dataset, workspace_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download GEO supplementary files and register them as a dataset.")
    parser.add_argument("--accession", required=True)
    parser.add_argument("--dataset-id", default="")
    parser.add_argument("--array-type", default="AUTO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_id = args.dataset_id or args.accession.lower()
    geo_root = workspace_root() / "data" / "geo" / dataset_id
    geo_root.mkdir(parents=True, exist_ok=True)

    expr = (
        "suppressPackageStartupMessages(library(GEOquery)); "
        f"getGEOSuppFiles('{args.accession}', baseDir='{str(geo_root)}', makeDirectory=FALSE)"
    )
    subprocess.run(["Rscript", "-e", expr], check=True)

    for archive in list(geo_root.glob("*.zip")) + list(geo_root.glob("*.tar")) + list(geo_root.glob("*.tar.gz")) + list(geo_root.glob("*.tgz")):
        subprocess.run(["python3", "-c", "import shutil,sys; shutil.unpack_archive(sys.argv[1], sys.argv[2])", str(archive), str(geo_root)], check=True)

    doc = load_registry()
    try:
        stored = str(geo_root.relative_to(workspace_root()))
    except ValueError:
        stored = str(geo_root)
    upsert_dataset(
        doc,
        dataset_id,
        {
            "source": "geo",
            "accession": args.accession,
            "path": stored,
            "array_type": args.array_type,
            "enabled": True,
        },
    )
    save_registry(doc)
    print(f"[INFO] Downloaded GEO supplementary files for {args.accession} into {stored}")
    print(f"[INFO] Registered dataset {dataset_id} in config/datasets.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
