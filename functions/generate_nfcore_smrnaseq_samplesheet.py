from __future__ import annotations

import csv
import hashlib
import importlib.util
import os
import re
from pathlib import Path

try:
    from functions._demux_common import (
        READ1_SUFFIXES,
        READ2_SUFFIXES,
        is_unassigned_sample,
        latest_demux_fastq_files,
        read_suffix,
    )
except ModuleNotFoundError:
    spec = importlib.util.spec_from_file_location("_demux_common", Path(__file__).with_name("_demux_common.py"))
    if spec is None or spec.loader is None:
        raise
    _demux_common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_demux_common)
    READ1_SUFFIXES = _demux_common.READ1_SUFFIXES
    READ2_SUFFIXES = _demux_common.READ2_SUFFIXES
    is_unassigned_sample = _demux_common.is_unassigned_sample
    latest_demux_fastq_files = _demux_common.latest_demux_fastq_files
    read_suffix = _demux_common.read_suffix


def _cache_root() -> Path:
    linkar_home = os.getenv("LINKAR_HOME", "").strip()
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "generated_samplesheets"
    return Path.home().resolve() / ".linkar" / "generated_samplesheets"


def _sample_name(path: Path, suffix: str) -> str:
    name = path.name[: -len(suffix)]
    return re.sub(r"_S\d+$", "", name)


def resolve(ctx) -> str:
    if ctx.project is None:
        raise RuntimeError("samplesheet generation requires a Linkar project with prior demultiplex outputs")

    fastq_files = sorted(Path(item).resolve() for item in latest_demux_fastq_files(ctx))
    if not fastq_files:
        raise RuntimeError("demultiplex demux_fastq_files output is empty")

    reads: dict[str, dict[str, list[str]]] = {}
    usable_files: list[str] = []
    for path in fastq_files:
        if not path.exists():
            raise RuntimeError(f"FASTQ file listed in demux_fastq_files does not exist: {path}")
        read1_suffix = read_suffix(path.name, READ1_SUFFIXES)
        read2_suffix = read_suffix(path.name, READ2_SUFFIXES)
        suffix = read1_suffix or read2_suffix
        if not suffix:
            continue
        sample = _sample_name(path, suffix)
        if not sample or is_unassigned_sample(sample):
            continue
        read = "R1" if read1_suffix else "R2"
        reads.setdefault(sample, {"R1": [], "R2": []})[read].append(str(path))
        usable_files.append(str(path))

    if not reads:
        raise RuntimeError("No usable FASTQ files found in demux_fastq_files")

    missing_r1 = sorted(sample for sample, pair in reads.items() if not pair["R1"])
    if missing_r1:
        raise RuntimeError(f"FASTQ pairing is invalid; samples have R2 but no R1: {', '.join(missing_r1)}")

    digest = hashlib.sha1("\n".join(sorted(usable_files)).encode("utf-8")).hexdigest()[:12]
    out_dir = _cache_root() / "nfcore_smrnaseq" / digest
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "samplesheet.csv"

    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample", "fastq_1", "fastq_2"])
        for sample, pair in sorted(reads.items()):
            if len(pair["R2"]) > len(pair["R1"]):
                raise RuntimeError(f"FASTQ pairing is invalid for {sample}: more R2 files than R1 files")
            for index, r1 in enumerate(pair["R1"]):
                r2 = pair["R2"][index] if index < len(pair["R2"]) else ""
                writer.writerow([sample, r1, r2])

    return str(out_csv.resolve())
