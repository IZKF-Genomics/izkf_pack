from __future__ import annotations

import csv
import hashlib
import importlib.util
import os
import re
from pathlib import Path

try:
    from functions._demux_common import is_unassigned_sample, latest_demux_fastq_files
except ModuleNotFoundError:
    spec = importlib.util.spec_from_file_location("_demux_common", Path(__file__).with_name("_demux_common.py"))
    if spec is None or spec.loader is None:
        raise
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    is_unassigned_sample = module.is_unassigned_sample
    latest_demux_fastq_files = module.latest_demux_fastq_files


FASTQ_RE = re.compile(
    r"^(?P<library>.+?)(?:_S\d+)?(?:_L\d{3})?_R(?P<read>[12])(?:_\d{3})?\.f(?:ast)?q\.gz$"
)
LIBRARY_RE = re.compile(r"^(?P<sample>.+)_(?P<kind>GEX|FB)$", re.IGNORECASE)
FIELDS = ["sample", "gex_fastq_id", "gex_fastqs", "feature_fastq_id", "feature_fastqs", "feature_types"]


def _cache_root() -> Path:
    linkar_home = str(os.getenv("LINKAR_HOME") or "").strip()
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "generated_samplesheets"
    return Path.home().resolve() / ".linkar" / "generated_samplesheets"


def _from_demultiplex(ctx) -> list[Path]:
    try:
        return sorted(Path(item).resolve() for item in latest_demux_fastq_files(ctx))
    except RuntimeError:
        return []


def _from_nfcore_scrnaseq(ctx) -> list[Path]:
    project = getattr(ctx, "project", None)
    if project is None:
        return []
    entries = (getattr(project, "data", {}) or {}).get("templates") or []
    for entry in reversed(entries):
        if not isinstance(entry, dict) or entry.get("id") != "nfcore_scrnaseq":
            continue
        candidates = []
        outputs = entry.get("outputs") or {}
        if outputs.get("input_samplesheet"):
            candidates.append(Path(str(outputs["input_samplesheet"])))
        workspace = Path(str(entry.get("path") or ""))
        project_root = Path(getattr(project, "root", "") or getattr(project, "path", "") or ".")
        if workspace and not workspace.is_absolute():
            workspace = project_root / workspace
        candidates.append(workspace / "samplesheet.csv")
        for candidate in candidates:
            if not candidate.exists():
                continue
            paths: list[Path] = []
            with candidate.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    for key in ("fastq_1", "fastq_2"):
                        value = str(row.get(key) or "").strip()
                        if value:
                            paths.append(Path(value).expanduser().resolve())
            if paths:
                return sorted(set(paths))
    return []


def build_rows(fastq_files: list[Path]) -> list[dict[str, str]]:
    libraries: dict[str, dict[str, object]] = {}
    for path in fastq_files:
        match = FASTQ_RE.match(path.name)
        if not match:
            continue
        library_id = match.group("library")
        if is_unassigned_sample(library_id) or library_id.lower().startswith("phix"):
            continue
        library_match = LIBRARY_RE.match(library_id)
        if not library_match:
            continue
        sample = library_match.group("sample")
        kind = library_match.group("kind").upper()
        record = libraries.setdefault(
            library_id,
            {"sample": sample, "kind": kind, "dirs": set(), "reads": set()},
        )
        record["dirs"].add(str(path.parent))
        record["reads"].add(match.group("read"))

    paired: dict[str, dict[str, dict[str, object]]] = {}
    for library_id, record in libraries.items():
        reads = record["reads"]
        if reads != {"1", "2"}:
            raise RuntimeError(f"FASTQ library {library_id} does not contain both R1 and R2 files")
        dirs = record["dirs"]
        if len(dirs) != 1:
            raise RuntimeError(f"FASTQ library {library_id} spans multiple directories, which is not supported")
        sample = str(record["sample"])
        kind = str(record["kind"])
        if kind in paired.setdefault(sample, {}):
            raise RuntimeError(f"Multiple {kind} libraries were discovered for sample {sample}")
        paired[sample][kind] = {"id": library_id, "dir": next(iter(dirs))}

    if not paired:
        raise RuntimeError(
            "No paired libraries ending in _GEX and _FB were found. "
            "Rename libraries or provide config/samples.csv after rendering."
        )

    rows: list[dict[str, str]] = []
    incomplete = []
    for sample, pair in sorted(paired.items()):
        if "GEX" not in pair or "FB" not in pair:
            incomplete.append(f"{sample} ({', '.join(sorted(pair))})")
            continue
        rows.append(
            {
                "sample": sample,
                "gex_fastq_id": str(pair["GEX"]["id"]),
                "gex_fastqs": str(pair["GEX"]["dir"]),
                "feature_fastq_id": str(pair["FB"]["id"]),
                "feature_fastqs": str(pair["FB"]["dir"]),
                "feature_types": "Antibody Capture",
            }
        )
    if incomplete:
        raise RuntimeError("Unpaired GEX/FB libraries: " + "; ".join(incomplete))
    return rows


def resolve(ctx) -> str:
    fastq_files = _from_demultiplex(ctx) or _from_nfcore_scrnaseq(ctx)
    if not fastq_files:
        raise RuntimeError(
            "cellranger multi samplesheet could not be generated: no demultiplex FASTQs or "
            "nfcore_scrnaseq samplesheet were found in the current project"
        )
    for path in fastq_files:
        if not path.exists():
            raise RuntimeError(f"FASTQ file does not exist: {path}")
    rows = build_rows(fastq_files)
    digest = hashlib.sha1("\n".join(str(path) for path in fastq_files).encode()).hexdigest()[:12]
    out_dir = _cache_root() / "cellranger_multi" / digest
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "samples.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return str(out_csv.resolve())
