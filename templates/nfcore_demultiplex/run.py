#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import shlex
import shutil
from pathlib import Path


TRUTHY_VALUES = {"1", "true", "yes", "on"}
FALSY_VALUES = {"0", "false", "no", "off", "none", "null", "na", "n/a"}
PLATFORMS = {"auto", "illumina", "aviti"}
DEMULTIPLEXERS = {"auto", "bclconvert", "bases2fastq"}
PLACEHOLDER_SAMPLE_PATTERNS = (
    re.compile(r"^example", re.IGNORECASE),
    re.compile(r"^test", re.IGNORECASE),
)
PLACEHOLDER_INDEXES = {"AAAAAAAAAA", "TTTTTTTTTT", "CCCCCCCCCC", "GGGGGGGGGG"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the nf-core/demultiplex workspace.")
    parser.add_argument(
        "--prepare",
        "--prepare-only",
        action="store_true",
        help="Copy the flowcell samplesheet and write config/run_params.env.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"[error] required environment variable is missing: {name}")
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def normalize_memory(value: str) -> str:
    memory = value.strip()
    if memory.upper().endswith("GB"):
        return f"{memory[:-2]}.GB"
    return memory


def normalize_int(value: str, *, name: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        parsed = int(text)
    except ValueError as exc:
        raise SystemExit(f"[error] expected integer-like value for {name}, got: {value}") from exc
    if parsed < 1:
        raise SystemExit(f"[error] expected {name} to be >= 1, got: {value}")
    return str(parsed)


def normalize_bool(value: str, *, default: bool) -> str:
    text = value.strip()
    if not text:
        return "true" if default else "false"
    lowered = text.lower()
    if lowered in TRUTHY_VALUES:
        return "true"
    if lowered in FALSY_VALUES:
        return "false"
    raise SystemExit(f"[error] expected a boolean-like value, got: {value}")


def shell_assign(name: str, value: str) -> str:
    return f"{name}={shlex.quote(value)}"


def parse_flowcell_id(raw_run_dir: Path, *, platform: str) -> str:
    base = raw_run_dir.name.strip()
    if not base:
        return ""
    if platform == "aviti":
        return base
    parts = base.split("_")
    last = parts[-1] if parts else base
    if re.fullmatch(r"A[A-Z0-9]+", last):
        return last[1:]
    return last


def detect_platform(raw_run_dir: Path) -> str:
    if (raw_run_dir / "RunManifest.csv").is_file():
        return "aviti"
    illumina_markers = [
        raw_run_dir / "RunInfo.xml",
        raw_run_dir / "Data" / "Intensities" / "BaseCalls",
        raw_run_dir / "InterOp",
        raw_run_dir / "RTAComplete.txt",
        raw_run_dir / "CopyComplete.txt",
    ]
    if any(path.exists() for path in illumina_markers):
        return "illumina"
    return ""


def resolve_platform(raw_run_dir: Path, platform: str) -> str:
    normalized = platform.strip().lower() or "auto"
    if normalized not in PLATFORMS:
        allowed = ", ".join(sorted(PLATFORMS))
        raise SystemExit(f"[error] unsupported platform '{platform}'. Use one of: {allowed}")
    if normalized != "auto":
        return normalized
    detected = detect_platform(raw_run_dir)
    if detected:
        return detected
    raise SystemExit(
        "[error] could not infer platform from raw_run_dir. "
        "Pass --platform illumina or --platform aviti, or set --demultiplexer explicitly."
    )


def resolve_demultiplexer(raw_run_dir: Path, platform: str, demultiplexer: str) -> tuple[str, str]:
    normalized = demultiplexer.strip().lower() or "auto"
    if normalized not in DEMULTIPLEXERS:
        allowed = ", ".join(sorted(DEMULTIPLEXERS))
        raise SystemExit(f"[error] unsupported demultiplexer '{demultiplexer}'. Use one of: {allowed}")
    if normalized != "auto":
        resolved_platform = platform.strip().lower() or "auto"
        if resolved_platform == "auto":
            resolved_platform = detect_platform(raw_run_dir) or "manual"
        return resolved_platform, normalized
    resolved_platform = resolve_platform(raw_run_dir, platform)
    if resolved_platform == "illumina":
        return resolved_platform, "bclconvert"
    if resolved_platform == "aviti":
        return resolved_platform, "bases2fastq"
    raise SystemExit(f"[error] unsupported resolved platform: {resolved_platform}")


def resolve_flowcell_samplesheet(raw_run_dir: Path, platform: str, explicit: str) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"[error] flowcell_samplesheet does not exist: {path}")
        return path
    if platform == "aviti":
        path = raw_run_dir / "RunManifest.csv"
        if path.exists():
            return path.resolve()
        raise SystemExit(
            f"[error] AVITI runs default to raw_run_dir/RunManifest.csv, but it was not found: {path}"
        )
    fallback = raw_run_dir / "SampleSheet.csv"
    if fallback.exists():
        return fallback.resolve()
    raise SystemExit(
        "[error] flowcell_samplesheet is unresolved. Pass --flowcell-samplesheet or use --binding default."
    )


def resolve_skip_tools(value: str, *, demultiplexer: str) -> str:
    tools = [item.strip() for item in value.split(",") if item.strip()]
    if demultiplexer == "bases2fastq" and "multiqc" not in tools:
        tools.append("multiqc")
    return ",".join(tools)


def row_value(row: dict[str, str], *keys: str) -> str:
    lower_map = {key.lower(): value for key, value in row.items()}
    for key in keys:
        value = lower_map.get(key.lower(), "")
        if value.strip():
            return value.strip()
    return ""


def is_placeholder_row(header: list[str], raw_row: list[str]) -> bool:
    padded = raw_row + [""] * max(0, len(header) - len(raw_row))
    row = {key.strip(): value.strip() for key, value in zip(header, padded)}
    sample = row_value(row, "SampleName", "Sample_Name", "Sample_ID", "SampleID", "Sample")
    index1 = row_value(row, "Index1", "index", "I7_Index_ID")
    index2 = row_value(row, "Index2", "index2", "I5_Index_ID")
    has_placeholder_name = any(pattern.search(sample) for pattern in PLACEHOLDER_SAMPLE_PATTERNS)
    has_placeholder_index = index1.upper() in PLACEHOLDER_INDEXES or index2.upper() in PLACEHOLDER_INDEXES
    return has_placeholder_name and has_placeholder_index


def comment_placeholder_rows(path: Path) -> int:
    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    section = ""
    header: list[str] | None = None
    changed = 0
    output: list[str] = []

    for line in lines:
        parsed = next(csv.reader([line]))
        if not parsed or not any(cell.strip() for cell in parsed):
            output.append(line)
            continue
        first = parsed[0].strip()
        if first.startswith("#"):
            output.append(line)
            continue
        if first.startswith("[") and first.endswith("]"):
            section = first.strip("[]").lower()
            header = None
            output.append(line)
            continue
        if section not in {"samples", "data"}:
            output.append(line)
            continue
        if header is None:
            header = [cell.strip() for cell in parsed]
            output.append(line)
            continue
        if is_placeholder_row(header, parsed):
            output.append(f"# {line}")
            changed += 1
        else:
            output.append(line)

    if changed:
        path.write_text("".join(output), encoding="utf-8")
    return changed


def copy_samplesheet(source: Path, destination: Path, *, platform: str) -> int:
    if source.resolve() == destination.resolve():
        copied = False
    else:
        shutil.copy2(source, destination)
        copied = True
    commented_rows = comment_placeholder_rows(destination) if platform == "aviti" else 0
    if commented_rows:
        action = "copied and filtered" if copied else "filtered"
        print(
            f"[info] {action} flowcell_samplesheet.csv: commented {commented_rows} AVITI placeholder row(s)",
            flush=True,
        )
    return commented_rows


def write_runtime_env(
    output_path: Path,
    *,
    raw_run_dir: Path,
    flowcell_id: str,
    flowcell_lane: str,
    merge_lanes: str,
    platform: str,
    demultiplexer: str,
    skip_tools: str,
    v1_schema: str,
    remove_samplesheet_adapter: str,
    project_multiqc: str,
    allow_empty_fastq: str,
    max_cpus: str,
    max_memory: str,
    demux_cpus: str,
    falco_cpus: str,
    pack_root: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated by run.py. Edit values here before rerunning.",
        shell_assign("RAW_RUN_DIR", str(raw_run_dir)),
        shell_assign("FLOWCELL_ID", flowcell_id),
        shell_assign("FLOWCELL_LANE", flowcell_lane),
        shell_assign("MERGE_LANES", merge_lanes),
        shell_assign("PLATFORM", platform),
        shell_assign("DEMULTIPLEXER", demultiplexer),
        shell_assign("SKIP_TOOLS", skip_tools),
        shell_assign("V1_SCHEMA", v1_schema),
        shell_assign("REMOVE_SAMPLESHEET_ADAPTER", remove_samplesheet_adapter),
        shell_assign("PROJECT_MULTIQC", project_multiqc),
        shell_assign("ALLOW_EMPTY_FASTQ", allow_empty_fastq),
        shell_assign("MAX_CPUS", str(max_cpus)),
        shell_assign("MAX_MEMORY", normalize_memory(max_memory) if max_memory else ""),
        shell_assign("DEMUX_CPUS", normalize_int(demux_cpus, name="DEMUX_CPUS")),
        shell_assign("FALCO_CPUS", normalize_int(falco_cpus, name="FALCO_CPUS")),
        shell_assign("PACK_ROOT", str(pack_root)),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def prepare() -> None:
    script_dir = Path(__file__).resolve().parent
    pack_root = Path(os.environ.get("LINKAR_PACK_ROOT") or script_dir.parent.parent).resolve()
    raw_run_dir = Path(require_env("RAW_RUN_DIR")).expanduser().resolve()
    if not raw_run_dir.exists():
        raise SystemExit(f"[error] raw_run_dir does not exist: {raw_run_dir}")

    platform, demultiplexer = resolve_demultiplexer(
        raw_run_dir,
        optional_env("PLATFORM", "auto"),
        optional_env("DEMULTIPLEXER", "auto"),
    )
    flowcell_samplesheet = resolve_flowcell_samplesheet(
        raw_run_dir,
        platform,
        optional_env("FLOWCELL_SAMPLESHEET"),
    )
    flowcell_id = optional_env("FLOWCELL_ID") or parse_flowcell_id(raw_run_dir, platform=platform)

    copy_samplesheet(flowcell_samplesheet, script_dir / "flowcell_samplesheet.csv", platform=platform)
    run_params = script_dir / "config" / "run_params.env"
    write_runtime_env(
        run_params,
        raw_run_dir=raw_run_dir,
        flowcell_id=flowcell_id,
        flowcell_lane=optional_env("FLOWCELL_LANE"),
        merge_lanes=normalize_bool(optional_env("MERGE_LANES"), default=True),
        platform=platform,
        demultiplexer=demultiplexer,
        skip_tools=resolve_skip_tools(optional_env("SKIP_TOOLS"), demultiplexer=demultiplexer),
        v1_schema=normalize_bool(optional_env("V1_SCHEMA"), default=True),
        remove_samplesheet_adapter=normalize_bool(optional_env("REMOVE_SAMPLESHEET_ADAPTER"), default=False),
        project_multiqc=normalize_bool(optional_env("PROJECT_MULTIQC"), default=True),
        allow_empty_fastq=normalize_bool(optional_env("ALLOW_EMPTY_FASTQ"), default=False),
        max_cpus=optional_env("MAX_CPUS"),
        max_memory=optional_env("MAX_MEMORY"),
        demux_cpus=optional_env("DEMUX_CPUS"),
        falco_cpus=optional_env("FALCO_CPUS"),
        pack_root=pack_root,
    )
    print(f"[info] wrote {run_params.relative_to(script_dir)}", flush=True)


def main() -> int:
    parse_args()
    prepare()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
