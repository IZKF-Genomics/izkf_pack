#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build adoptable per-Sample_Project views for a demultiplex run."
    )
    parser.add_argument("--results-dir", required=True, type=Path)
    return parser.parse_args()


def replace_symlink(link: Path, target: Path) -> None:
    if link.is_symlink() or link.exists():
        if link.is_dir() and not link.is_symlink():
            shutil.rmtree(link)
        else:
            link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target.resolve(), target_is_directory=target.is_dir())


def fastq_files(project_dir: Path) -> list[Path]:
    return sorted(
        path.resolve()
        for pattern in ("*.fastq.gz", "*.fq.gz", "*.fastq", "*.fq")
        for path in project_dir.glob(pattern)
        if path.is_file()
    )


def load_contract(results_dir: Path) -> dict[str, object]:
    path = results_dir / "template_outputs.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    outputs = payload.get("outputs") if isinstance(payload, dict) else None
    return outputs if isinstance(outputs, dict) else {}


def map_value(mapping: object, key: str) -> str:
    if not isinstance(mapping, dict):
        return ""
    value = mapping.get(key)
    return str(value or "").strip()


def build_outputs(
    *,
    view_dir: Path,
    project: str,
    project_dir: Path,
    contract: dict[str, object],
) -> dict[str, object]:
    view_results = view_dir / "results"
    output_dir = view_results / "output"
    qc_dir = view_results / "qc"
    multiqc_report = view_results / "multiqc" / "multiqc_report.html"
    contamination_dir = qc_dir / "contamination"

    outputs: dict[str, object] = {
        "results_dir": str(view_results.resolve()),
        "output_dir": str(output_dir.resolve()),
        "demux_fastq_files": [
            str((output_dir / path.name).resolve()) for path in fastq_files(project_dir)
        ],
        "qc_dir": str(qc_dir.resolve()) if qc_dir.exists() else None,
        "project_qc_dirs": {project: str(qc_dir.resolve())} if qc_dir.exists() else {},
        "contamination_dir": (
            str(contamination_dir.resolve()) if contamination_dir.exists() else None
        ),
        "project_contamination_dirs": (
            {project: str(contamination_dir.resolve())}
            if contamination_dir.exists()
            else {}
        ),
        "multiqc_report": str(multiqc_report.resolve())
        if multiqc_report.exists()
        else None,
        "project_multiqc_reports": (
            {project: str(multiqc_report.resolve())}
            if multiqc_report.exists()
            else {}
        ),
        "sample_project": project,
        "source_results_dir": str(project_dir.parent.parent.resolve()),
        "source_output_dir": str(project_dir.resolve()),
    }

    source_report = map_value(contract.get("project_multiqc_reports"), project)
    if source_report and not outputs["multiqc_report"]:
        outputs["multiqc_report"] = source_report
        outputs["project_multiqc_reports"] = {project: source_report}

    return outputs


def write_view_metadata(view_dir: Path, outputs: dict[str, object], project: str) -> None:
    meta = {
        "id": "demultiplex",
        "template": "demultiplex",
        "source_template": "demultiplex",
        "params": {"sample_project": project},
        "outputs": outputs,
    }
    linkar_dir = view_dir / ".linkar"
    linkar_dir.mkdir(parents=True, exist_ok=True)
    (linkar_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (view_dir / "results" / "template_outputs.json").write_text(
        json.dumps(
            {"outdir": str(view_dir / "results"), "outputs": outputs},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def build_view(results_dir: Path, project_dir: Path, contract: dict[str, object]) -> Path:
    project = project_dir.name
    view_dir = results_dir / "project_views" / project
    view_results = view_dir / "results"
    view_results.mkdir(parents=True, exist_ok=True)

    replace_symlink(view_results / "output", project_dir)
    qc_dir = project_dir / "qc"
    if qc_dir.exists():
        replace_symlink(view_results / "qc", qc_dir)
    multiqc_dir = qc_dir / "multiqc"
    if multiqc_dir.exists():
        replace_symlink(view_results / "multiqc", multiqc_dir)

    outputs = build_outputs(
        view_dir=view_dir,
        project=project,
        project_dir=project_dir,
        contract=contract,
    )
    write_view_metadata(view_dir, outputs, project)
    return view_dir


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    output_root = results_dir / "output"
    views_root = results_dir / "project_views"
    if views_root.exists():
        shutil.rmtree(views_root)
    if not output_root.exists():
        return 0

    contract = load_contract(results_dir)
    views = []
    for project_dir in sorted(path for path in output_root.iterdir() if path.is_dir()):
        if not fastq_files(project_dir):
            continue
        views.append(build_view(results_dir, project_dir, contract))

    if views:
        print("Built demultiplex project views:")
        for view in views:
            print(f"- {view}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
