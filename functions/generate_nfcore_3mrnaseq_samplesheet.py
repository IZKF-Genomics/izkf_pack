from __future__ import annotations

import csv
import hashlib
import os
import re
from pathlib import Path


READ1_EXTENSION = "_R1_001.fastq.gz"
READ2_EXTENSION = "_R2_001.fastq.gz"


def _nonempty(value: object | None) -> str:
    return str(value or "").strip()


def _cache_root() -> Path:
    linkar_home = _nonempty(os.getenv("LINKAR_HOME"))
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "generated_samplesheets"
    return Path.home().resolve() / ".linkar" / "generated_samplesheets"


def _strip_sample_suffix(name: str) -> str:
    return re.sub(r"_S\d+$", "", name)


def _latest_demux_results_dir(ctx) -> Path:
    latest = ctx.latest_output("results_dir", template_id="demultiplex")
    if not latest:
        raise RuntimeError(
            "samplesheet could not be generated because no demultiplex results_dir was found in the current project"
        )
    path = Path(str(latest)).resolve()
    if not path.exists():
        raise RuntimeError(f"demultiplex results_dir does not exist: {path}")
    return path


def _demux_fastq_dir(ctx) -> Path:
    results_dir = _latest_demux_results_dir(ctx)
    candidate = results_dir / "output"
    if candidate.exists():
        return candidate
    return results_dir


def resolve(ctx) -> str:
    if ctx.project is None:
        raise RuntimeError("samplesheet generation requires a Linkar project with prior demultiplex outputs")

    fastq_dir = _demux_fastq_dir(ctx)
    r1_files = sorted(fastq_dir.rglob(f"*{READ1_EXTENSION}"))
    if not r1_files:
        raise RuntimeError(f"No R1 FASTQ files found under {fastq_dir}")

    reads: dict[str, dict[str, list[str]]] = {}
    for path in r1_files:
        sample = _strip_sample_suffix(path.name[: -len(READ1_EXTENSION)])
        if sample.startswith("Undetermined"):
            continue
        reads.setdefault(sample, {"R1": [], "R2": []})["R1"].append(str(path.resolve()))

    r2_files = sorted(fastq_dir.rglob(f"*{READ2_EXTENSION}"))
    for path in r2_files:
        sample = _strip_sample_suffix(path.name[: -len(READ2_EXTENSION)])
        if sample.startswith("Undetermined"):
            continue
        reads.setdefault(sample, {"R1": [], "R2": []})["R2"].append(str(path.resolve()))

    if not reads:
        raise RuntimeError(f"No usable FASTQ pairs found under {fastq_dir}")

    cache_key = hashlib.sha1(str(fastq_dir).encode("utf-8")).hexdigest()[:12]
    out_dir = _cache_root() / "nfcore_3mrnaseq" / cache_key
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "samplesheet.csv"

    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample", "fastq_1", "fastq_2", "strandedness"])
        for sample, pair in sorted(reads.items()):
            for index, r1 in enumerate(pair["R1"]):
                r2 = pair["R2"][index] if index < len(pair["R2"]) else ""
                writer.writerow([sample, r1, r2, "forward"])

    return str(out_csv.resolve())
