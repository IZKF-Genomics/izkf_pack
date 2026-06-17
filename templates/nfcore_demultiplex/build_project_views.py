#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path


FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
SKIP_DIR_NAMES = {"work", "output", ".nextflow", ".git", ".pixi"}
PROJECT_KEYS = ("Sample_Project", "SampleProject", "Project", "ProjectName", "Project_Name")
SAMPLE_KEYS = ("Sample_ID", "SampleID", "Sample_Name", "SampleName", "Sample")
DEFAULT_PROJECT = "fastq"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write project-level FASTQ views and adoption metadata for nf-core/demultiplex."
    )
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--flowcell-samplesheet", required=True, type=Path)
    parser.add_argument("--project-multiqc", default="true")
    parser.add_argument("--allow-empty-fastq", default="false")
    return parser.parse_args()


def is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def sanitize_name(value: str, *, fallback: str) -> str:
    text = value.strip() or fallback
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._") or fallback


def parse_sectioned_csv(path: Path) -> list[tuple[str, list[dict[str, str]]]]:
    sections: list[tuple[str, list[dict[str, str]]]] = []
    section = ""
    header: list[str] | None = None
    rows: list[dict[str, str]] = []

    def flush() -> None:
        nonlocal rows
        if section and rows:
            sections.append((section, rows))
        rows = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        for raw_row in csv.reader(handle):
            if not raw_row or not any(cell.strip() for cell in raw_row):
                continue
            first = raw_row[0].strip()
            if first.startswith("#"):
                continue
            if first.startswith("[") and first.endswith("]"):
                flush()
                section = first.strip("[]")
                header = None
                continue
            if header is None:
                header = [cell.strip() for cell in raw_row]
                continue
            normalized = raw_row + [""] * max(0, len(header) - len(raw_row))
            rows.append({key: value.strip() for key, value in zip(header, normalized)})
    flush()
    return sections


def pick(row: dict[str, str], keys: tuple[str, ...]) -> str:
    lower_map = {key.lower(): value for key, value in row.items()}
    for key in keys:
        value = row.get(key) or lower_map.get(key.lower()) or ""
        if value.strip():
            return value.strip()
    return ""


def samplesheet_projects(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    sections = parse_sectioned_csv(path)
    candidate_sections = [item for item in sections if item[0].lower() in {"data", "samples"}]
    if not candidate_sections:
        candidate_sections = sections

    for _section, rows in candidate_sections:
        for row in rows:
            project = sanitize_name(pick(row, PROJECT_KEYS), fallback=DEFAULT_PROJECT)
            sample_values = {
                pick(row, ("Sample_ID", "SampleID", "Sample")),
                pick(row, ("Sample_Name", "SampleName")),
            }
            for sample in sample_values:
                sample = sample.strip()
                if sample:
                    mapping[sample] = project
    return mapping


def should_skip(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_DIR_NAMES for part in rel.parts)


def first_fastq_line(path: Path) -> str:
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="ascii", errors="replace") as handle:
                return (handle.readline() or "").strip()
        with path.open(encoding="ascii", errors="replace") as handle:
            return (handle.readline() or "").strip()
    except EOFError:
        return ""


def is_empty_fastq(path: Path) -> bool:
    return not first_fastq_line(path).startswith("@")


def all_fastqs(results_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for path in results_dir.rglob("*"):
        if not path.is_file() or should_skip(path, results_dir):
            continue
        if path.name.endswith(FASTQ_SUFFIXES):
            paths.append(path.resolve())
    return sorted(paths)


def token_matches(path: Path, sample: str) -> bool:
    haystack = str(path).lower()
    needle = sample.lower()
    return needle in haystack


def assign_fastqs(fastqs: list[Path], sample_projects: dict[str, str]) -> dict[str, list[Path]]:
    project_fastqs: dict[str, list[Path]] = defaultdict(list)
    matched: set[Path] = set()
    for sample, project in sample_projects.items():
        for fastq in fastqs:
            if fastq in matched:
                continue
            if token_matches(fastq, sample):
                project_fastqs[project].append(fastq)
                matched.add(fastq)
    for fastq in fastqs:
        if fastq not in matched:
            project_fastqs["unassigned"].append(fastq)
    return {project: sorted(paths) for project, paths in project_fastqs.items() if paths}


def safe_hardlink(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    destination.hardlink_to(source)


def unique_destination(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists() and not candidate.is_symlink():
        return candidate
    stem = Path(name).stem
    suffix = "".join(Path(name).suffixes)
    for index in range(2, 10000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise RuntimeError(f"could not create a unique destination for {name}")


def related_qc_paths(results_dir: Path, samples: list[str]) -> list[Path]:
    related: list[Path] = []
    sample_tokens = [sample.lower() for sample in samples if sample.strip()]
    if not sample_tokens:
        return related
    for path in results_dir.rglob("*"):
        if should_skip(path, results_dir) or path.is_dir():
            continue
        if path.name.endswith(FASTQ_SUFFIXES):
            continue
        text = str(path.relative_to(results_dir)).lower()
        if any(token in text for token in sample_tokens):
            related.append(path.resolve())
    return sorted(related)


def link_project_files(
    *,
    project_dir: Path,
    fastqs: list[Path],
    qc_paths: list[Path],
) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    for fastq in fastqs:
        safe_hardlink(fastq, unique_destination(project_dir, fastq.name))
    qc_input = project_dir / "qc" / "input"
    for path in qc_paths:
        safe_hardlink(path, unique_destination(qc_input, path.name))


def run_project_multiqc(project_dir: Path, project: str) -> None:
    outdir = project_dir / "qc" / "multiqc"
    outdir.mkdir(parents=True, exist_ok=True)
    command = [
        "pixi",
        "run",
        "multiqc",
        str(project_dir),
        "--outdir",
        str(outdir),
        "--filename",
        "multiqc_report.html",
        "--title",
        project,
        "--force",
    ]
    subprocess.run(command, check=True)


def fastq_outputs(project_dir: Path) -> list[str]:
    return [
        str(path.resolve())
        for pattern in ("*.fastq.gz", "*.fq.gz", "*.fastq", "*.fq")
        for path in sorted(project_dir.glob(pattern))
        if path.is_file() or path.is_symlink()
    ]


def first_glob(root: Path, pattern: str) -> str | None:
    matches = sorted(path for path in root.glob(pattern) if path.is_file())
    return str(matches[0].resolve()) if matches else None


def build_outputs(project_dir: Path) -> dict[str, object]:
    multiqc_report = project_dir / "qc" / "multiqc" / "multiqc_report.html"
    qc_dir = project_dir / "qc"
    results_dir = project_dir.parent.parent
    run_multiqc_report = first_glob(results_dir, "multiqc/*multiqc_report.html")
    return {
        "results_dir": str(project_dir.resolve()),
        "output_dir": str(project_dir.resolve()),
        "demux_fastq_files": fastq_outputs(project_dir),
        "qc_dir": str(qc_dir.resolve()) if qc_dir.exists() else None,
        "multiqc_report": str(multiqc_report.resolve()) if multiqc_report.exists() else None,
        "run_multiqc_report": run_multiqc_report,
        "nfcore_multiqc_report": run_multiqc_report,
    }


def write_project_metadata(project_dir: Path, project: str) -> None:
    outputs = build_outputs(project_dir)
    declared_outputs = {
        "results_dir": {"path": ".."},
        "output_dir": {"path": ".."},
        "demux_fastq_files": {"glob": "../*.fastq.gz"},
        "qc_dir": {"path": "../qc"},
        "multiqc_report": {"path": "../qc/multiqc/multiqc_report.html"},
        "run_multiqc_report": {"glob": "../../multiqc/*multiqc_report.html"},
        "nfcore_multiqc_report": {"glob": "../../multiqc/*multiqc_report.html"},
    }
    payload = {
        "declared_outputs": declared_outputs,
        "id": "nfcore_demultiplex",
        "instance_id": f"nfcore_demultiplex_{project}",
        "template": "nfcore_demultiplex",
        "source_template": "nfcore_demultiplex",
        "outdir": str(project_dir.resolve()),
        "params": {"sample_project": project},
        "outputs": outputs,
    }
    linkar_dir = project_dir / ".linkar"
    linkar_dir.mkdir(parents=True, exist_ok=True)
    (linkar_dir / "meta.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (project_dir / "template_outputs.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    output_root = results_dir / "output"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    sample_projects = samplesheet_projects(args.flowcell_samplesheet.resolve())
    fastqs = all_fastqs(results_dir)
    if not is_truthy(args.allow_empty_fastq):
        empty = [path for path in fastqs if is_empty_fastq(path)]
        if empty:
            joined = "\n".join(f"- {path}" for path in empty[:20])
            raise SystemExit(
                "[error] Empty FASTQ files were detected before building project views. "
                "Run check_empty_fastqs.py for a full report or set --allow-empty-fastq true.\n"
                f"{joined}"
            )
    fastqs = [path for path in fastqs if not is_empty_fastq(path)]
    project_fastqs = assign_fastqs(fastqs, sample_projects)
    samples_by_project: dict[str, list[str]] = defaultdict(list)
    for sample, project in sample_projects.items():
        samples_by_project[project].append(sample)

    project_dirs: list[Path] = []
    for project, paths in sorted(project_fastqs.items()):
        project_dir = output_root / sanitize_name(project, fallback=DEFAULT_PROJECT)
        qc_tokens = samples_by_project.get(project, [])
        if project == "unassigned":
            qc_tokens = [*qc_tokens, "Unassigned", "Undetermined"]
        qc_paths = related_qc_paths(results_dir, qc_tokens)
        link_project_files(project_dir=project_dir, fastqs=paths, qc_paths=qc_paths)
        if is_truthy(args.project_multiqc):
            run_project_multiqc(project_dir, project)
        write_project_metadata(project_dir, project)
        project_dirs.append(project_dir)

    if project_dirs:
        print("Wrote nf-core demultiplex project adoption metadata:")
        for project_dir in project_dirs:
            print(f"- {project_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
