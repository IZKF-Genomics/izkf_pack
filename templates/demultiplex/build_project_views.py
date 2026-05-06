#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write adoptable metadata into each demultiplex Sample_Project folder."
    )
    parser.add_argument("--results-dir", required=True, type=Path)
    return parser.parse_args()


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
    project: str,
    project_dir: Path,
    contract: dict[str, object],
) -> dict[str, object]:
    qc_dir = project_dir / "qc"
    multiqc_report = qc_dir / "multiqc" / "multiqc_report.html"
    contamination_dir = qc_dir / "contamination"

    outputs: dict[str, object] = {
        "results_dir": str(project_dir.resolve()),
        "output_dir": str(project_dir.resolve()),
        "demux_fastq_files": [
            str(path.resolve()) for path in fastq_files(project_dir)
        ],
        "qc_dir": str(qc_dir.resolve()) if qc_dir.exists() else None,
        "contamination_dir": (
            str(contamination_dir.resolve()) if contamination_dir.exists() else None
        ),
        "multiqc_report": str(multiqc_report.resolve())
        if multiqc_report.exists()
        else None,
    }

    source_report = map_value(contract.get("project_multiqc_reports"), project)
    if source_report and not outputs["multiqc_report"]:
        outputs["multiqc_report"] = source_report

    return outputs


def build_project_payload(
    project_dir: Path,
    outputs: dict[str, object],
    project: str,
) -> dict[str, object]:
    declared_outputs = {
        "results_dir": {"path": ".."},
        "output_dir": {"path": ".."},
        "demux_fastq_files": {"glob": "../*.fastq.gz"},
        "qc_dir": {"path": "../qc"},
        "contamination_dir": {"path": "../qc/contamination"},
        "multiqc_report": {"path": "../qc/multiqc/multiqc_report.html"},
    }
    return {
        "declared_outputs": declared_outputs,
        "id": "demultiplex",
        "instance_id": f"demultiplex_{project}",
        "template": "demultiplex",
        "source_template": "demultiplex",
        "outdir": str(project_dir.resolve()),
        "params": {"sample_project": project},
        "outputs": outputs,
    }


def write_project_metadata(project_dir: Path, outputs: dict[str, object], project: str) -> None:
    payload = build_project_payload(project_dir, outputs, project)
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


def build_project_metadata(project_dir: Path, contract: dict[str, object]) -> Path:
    project = project_dir.name
    outputs = build_outputs(
        project=project,
        project_dir=project_dir,
        contract=contract,
    )
    write_project_metadata(project_dir, outputs, project)
    return project_dir


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    output_root = results_dir / "output"
    legacy_views_root = results_dir / "project_views"
    if legacy_views_root.exists():
        shutil.rmtree(legacy_views_root)
    if not output_root.exists():
        return 0

    contract = load_contract(results_dir)
    projects = []
    for project_dir in sorted(path for path in output_root.iterdir() if path.is_dir()):
        if not fastq_files(project_dir):
            continue
        projects.append(build_project_metadata(project_dir, contract))

    if projects:
        print("Wrote demultiplex project adoption metadata:")
        for project_dir in projects:
            print(f"- {project_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
