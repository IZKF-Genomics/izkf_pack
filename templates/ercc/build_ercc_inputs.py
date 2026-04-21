#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import yaml


AUTHOR_PLACEHOLDER = "PROJECT_AUTHORS"


def _r_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _validate_samplesheet(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "sample" not in (reader.fieldnames or []):
            raise ValueError(f"samplesheet is missing required 'sample' column: {path}")
        samples = [str(row["sample"]).strip() for row in reader if str(row["sample"]).strip()]
    if not samples:
        raise ValueError(f"samplesheet contains no sample values: {path}")
    return samples


def _write_runtime_qmd(workspace_dir: Path, authors: str) -> None:
    template_path = workspace_dir / "ERCC.qmd"
    runtime_path = workspace_dir / "ERCC.runtime.qmd"
    runtime_text = template_path.read_text(encoding="utf-8").replace(
        AUTHOR_PLACEHOLDER,
        authors or AUTHOR_PLACEHOLDER,
    )
    runtime_path.write_text(runtime_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare ERCC Linkar runtime inputs.")
    parser.add_argument("--workspace-dir", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--salmon-dir", required=True)
    parser.add_argument("--samplesheet", required=True)
    parser.add_argument("--authors", default="")
    args = parser.parse_args()

    workspace_dir = Path(args.workspace_dir).resolve()
    results_dir = Path(args.results_dir).resolve()
    salmon_dir = Path(args.salmon_dir).resolve()
    samplesheet = Path(args.samplesheet).resolve()

    if not salmon_dir.is_dir():
        raise FileNotFoundError(f"salmon_dir does not exist: {salmon_dir}")
    salmon_tpm = salmon_dir / "salmon.merged.gene_tpm.tsv"
    if not salmon_tpm.is_file():
        raise FileNotFoundError(f"expected Salmon TPM table not found: {salmon_tpm}")
    if not samplesheet.is_file():
        raise FileNotFoundError(f"samplesheet does not exist: {samplesheet}")

    sample_names = _validate_samplesheet(samplesheet)
    results_dir.mkdir(parents=True, exist_ok=True)

    inputs_path = workspace_dir / "ercc_inputs.R"
    inputs_path.write_text(
        "\n".join(
            [
                f"salmon_dir <- {_r_string(str(salmon_dir))}",
                f"salmon_tpm_path <- {_r_string(str(salmon_tpm))}",
                f"samplesheet_path <- {_r_string(str(samplesheet))}",
                f"results_dir <- {_r_string(str(results_dir))}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    _write_runtime_qmd(workspace_dir, args.authors.strip())

    run_info = {
        "template": "ercc",
        "workspace_dir": str(workspace_dir),
        "results_dir": str(results_dir),
        "params": {
            "salmon_dir": str(salmon_dir),
            "samplesheet": str(samplesheet),
            "authors": args.authors.strip(),
            "sample_count": len(sample_names),
        },
        "inputs": {
            "salmon_tpm": str(salmon_tpm),
            "samplesheet": str(samplesheet),
        },
    }
    (results_dir / "run_info.yaml").write_text(yaml.safe_dump(run_info, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
