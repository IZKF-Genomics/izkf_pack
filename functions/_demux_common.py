from __future__ import annotations

from pathlib import Path
from typing import Any


DEMUX_TEMPLATE_IDS = ("nfcore_demultiplex", "demultiplex")
READ1_SUFFIXES = ("_R1_001.fastq.gz", "_R1.fastq.gz")
READ2_SUFFIXES = ("_R2_001.fastq.gz", "_R2.fastq.gz")
UNASSIGNED_PREFIXES = ("Undetermined", "Unassigned")


def _template_id(entry: dict[str, Any]) -> str:
    return str(entry.get("id") or entry.get("source_template") or "")


def _history(ctx: Any) -> list[dict[str, Any]]:
    project = getattr(ctx, "project", None)
    if project is None:
        return []
    data = getattr(project, "data", {}) or {}
    templates = data.get("templates") or []
    return [entry for entry in templates if isinstance(entry, dict)]


def latest_demux_output(ctx: Any, key: str) -> Any:
    for entry in reversed(_history(ctx)):
        if _template_id(entry) not in DEMUX_TEMPLATE_IDS:
            continue
        outputs = entry.get("outputs") or {}
        if isinstance(outputs, dict) and key in outputs:
            return outputs[key]

    latest_output = getattr(ctx, "latest_output", None)
    if callable(latest_output):
        for template_id in DEMUX_TEMPLATE_IDS:
            latest = latest_output(key, template_id=template_id)
            if latest:
                return latest
    return None


def latest_demux_fastq_files(ctx: Any) -> list[str]:
    latest = latest_demux_output(ctx, "demux_fastq_files")
    if not latest:
        raise RuntimeError(
            "samplesheet could not be generated because no demultiplex demux_fastq_files output "
            "was found in the current project"
        )
    if not isinstance(latest, list):
        raise RuntimeError("demultiplex demux_fastq_files output must be a list of file paths")
    return [str(item) for item in latest if str(item).strip()]


def latest_demux_results_dir(ctx: Any) -> Path:
    latest = latest_demux_output(ctx, "results_dir")
    if not latest:
        raise RuntimeError(
            "samplesheet could not be generated because no demultiplex results_dir was found in the current project"
        )
    path = Path(str(latest)).resolve()
    if not path.exists():
        raise RuntimeError(f"demultiplex results_dir does not exist: {path}")
    return path


def read_suffix(name: str, suffixes: tuple[str, ...]) -> str:
    for suffix in suffixes:
        if name.endswith(suffix):
            return suffix
    return ""


def is_unassigned_sample(sample: str) -> bool:
    return sample.startswith(UNASSIGNED_PREFIXES)
