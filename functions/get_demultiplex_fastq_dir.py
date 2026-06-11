from __future__ import annotations

import importlib.util
from pathlib import Path

try:
    from functions._demux_common import is_unassigned_sample, latest_demux_fastq_files
except ModuleNotFoundError:
    spec = importlib.util.spec_from_file_location("_demux_common", Path(__file__).with_name("_demux_common.py"))
    if spec is None or spec.loader is None:
        raise
    _demux_common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_demux_common)
    is_unassigned_sample = _demux_common.is_unassigned_sample
    latest_demux_fastq_files = _demux_common.latest_demux_fastq_files


def resolve(ctx) -> str:
    latest = latest_demux_fastq_files(ctx)
    paths = [Path(item).resolve() for item in latest]
    sample_paths = [path for path in paths if not is_unassigned_sample(path.name)]
    candidates = sample_paths or paths
    parents = {str(path.parent) for path in candidates}
    if not parents:
        raise RuntimeError("demultiplex demux_fastq_files output is empty")
    if len(parents) == 1:
        return next(iter(parents))

    nested_parents = sorted(parent for parent in parents if Path(parent).name)
    if nested_parents:
        deepest = max(nested_parents, key=lambda item: len(Path(item).parts))
        if all(Path(parent) == Path(deepest) or Path(parent) == Path(deepest).parent for parent in parents):
            return deepest

    if len(parents) != 1:
        joined = ", ".join(sorted(parents))
        raise RuntimeError(
            "fastq_dir could not be resolved because demultiplex demux_fastq_files spans multiple directories: "
            f"{joined}"
        )
    return next(iter(parents))
