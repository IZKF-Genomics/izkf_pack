from __future__ import annotations

import csv
import hashlib
import os
import re
from pathlib import Path


READ1_EXTENSION = "_R1_001.fastq.gz"
READ2_EXTENSION = "_R2_001.fastq.gz"
SAMPLE_SUFFIX_PATTERN = re.compile(r"_S\d+(?:_L\d{3})?$")


def _nonempty(value: object | None) -> str:
    return str(value or "").strip()


def _cache_root() -> Path:
    linkar_home = _nonempty(os.getenv("LINKAR_HOME"))
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "generated_samplesheets"
    return Path.home().resolve() / ".linkar" / "generated_samplesheets"


def _latest_demux_fastq_files(ctx) -> list[str]:
    latest = ctx.latest_output("demux_fastq_files", template_id="demultiplex")
    if not latest:
        raise RuntimeError(
            "samplesheet could not be generated because no demultiplex demux_fastq_files output was found in the current project"
        )
    if not isinstance(latest, list):
        raise RuntimeError("demultiplex demux_fastq_files output must be a list of file paths")
    return [str(item) for item in latest]


def _sample_key(path: Path, suffix: str) -> str:
    if not path.name.endswith(suffix):
        return ""
    return path.name[: -len(suffix)]


def _sample_name(pair_key: str) -> str:
    return SAMPLE_SUFFIX_PATTERN.sub("", pair_key)


def resolve(ctx) -> str:
    if ctx.project is None:
        raise RuntimeError("samplesheet generation requires a Linkar project with prior demultiplex outputs")

    fastq_files = sorted(Path(item).resolve() for item in _latest_demux_fastq_files(ctx))
    if not fastq_files:
        raise RuntimeError("demultiplex demux_fastq_files output is empty")

    reads: dict[str, dict[str, list[str]]] = {}
    usable_files: list[str] = []
    for path in fastq_files:
        if not path.exists():
            raise RuntimeError(f"FASTQ file listed in demux_fastq_files does not exist: {path}")
        if path.name.endswith(READ1_EXTENSION):
            pair_key = _sample_key(path, READ1_EXTENSION)
            sample = _sample_name(pair_key)
            if sample and not sample.startswith("Undetermined"):
                reads.setdefault(sample, {"R1": [], "R2": []})["R1"].append(str(path))
                usable_files.append(str(path))
        elif path.name.endswith(READ2_EXTENSION):
            pair_key = _sample_key(path, READ2_EXTENSION)
            sample = _sample_name(pair_key)
            if sample and not sample.startswith("Undetermined"):
                reads.setdefault(sample, {"R1": [], "R2": []})["R2"].append(str(path))
                usable_files.append(str(path))

    if not reads:
        raise RuntimeError("No usable FASTQ files found in demux_fastq_files")

    expected_cells = _nonempty((getattr(ctx, "resolved_params", {}) or {}).get("expected_cells"))
    digest_seed = "\n".join(sorted(usable_files)) + f"\nexpected_cells={expected_cells}"
    digest = hashlib.sha1(digest_seed.encode("utf-8")).hexdigest()[:12]
    out_dir = _cache_root() / "nfcore_scrnaseq" / digest
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "samplesheet.csv"

    fieldnames = ["sample", "fastq_1", "fastq_2"]
    if expected_cells:
        fieldnames.append("expected_cells")

    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for sample, pair in sorted(reads.items()):
            for index, r1 in enumerate(pair["R1"]):
                row = {
                    "sample": sample,
                    "fastq_1": r1,
                    "fastq_2": pair["R2"][index] if index < len(pair["R2"]) else "",
                }
                if expected_cells:
                    row["expected_cells"] = expected_cells
                writer.writerow(row)

    return str(out_csv.resolve())
