from __future__ import annotations

from pathlib import Path


def _latest_demux_fastq_files(ctx) -> list[str]:
    latest = ctx.latest_output("demux_fastq_files", template_id="demultiplex")
    if latest:
        if not isinstance(latest, list):
            raise RuntimeError("demultiplex demux_fastq_files output must be a list of file paths")
        return [str(item) for item in latest if str(item).strip()]

    if ctx.project is not None:
        data = getattr(ctx.project, "data", {}) or {}
        templates = data.get("templates") or []
        for entry in reversed(templates):
            if not isinstance(entry, dict):
                continue
            template_id = str(entry.get("id") or entry.get("source_template") or "")
            if template_id != "demultiplex":
                continue
            outputs = entry.get("outputs") or {}
            if not isinstance(outputs, dict):
                continue
            fallback = outputs.get("demux_fastq_files")
            if fallback:
                if not isinstance(fallback, list):
                    raise RuntimeError("demultiplex demux_fastq_files output must be a list of file paths")
                return [str(item) for item in fallback if str(item).strip()]
            break

    raise RuntimeError(
        "fastq_dir could not be resolved because no demultiplex demux_fastq_files output was found in the current project"
    )


def resolve(ctx) -> str:
    latest = _latest_demux_fastq_files(ctx)
    paths = [Path(item).resolve() for item in latest]
    sample_paths = [path for path in paths if not path.name.startswith("Undetermined")]
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
