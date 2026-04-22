#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path


PIPELINE_NAME = "nf-core/scrnaseq"
PIPELINE_VERSION = "4.1.0"
EXECUTION_PROFILE = "docker"
GENOME_PLACEHOLDER = "__EDIT_ME_GENOME__"
FASTA_PLACEHOLDER = "__EDIT_ME_FASTA__"
GTF_PLACEHOLDER = "__EDIT_ME_GTF__"
STAR_INDEX_PLACEHOLDER = "__EDIT_ME_STAR_INDEX__"
CELLRANGER_INDEX_PLACEHOLDER = "__EDIT_ME_CELLRANGER_INDEX__"
SUPPORTED_ALIGNERS = {"star", "cellranger"}
DEFAULT_CELLRANGER_PROTOCOL = "auto"
REFERENCE_MAP = {
    "GRCh38": {
        "fasta": "/data/ref_genomes/GRCh38/src/GRCh38.primary_assembly.genome.fa",
        "gtf": "/data/ref_genomes/GRCh38/src/gencode.v49.primary_assembly.annotation.gtf",
        "star_index": "/data/ref_genomes/GRCh38/indices/star",
        "cellranger_index": "/data/shared/10xGenomics/refs/refdata-gex-GRCh38-2024-A",
    },
    "GRCm39": {
        "fasta": "/data/ref_genomes/GRCm39/src/GRCm39.primary_assembly.genome.fa",
        "gtf": "/data/ref_genomes/GRCm39/src/gencode.vM38.primary_assembly.annotation.gtf",
        "star_index": "/data/ref_genomes/GRCm39/indices/star",
        "cellranger_index": "/data/shared/10xGenomics/refs/refdata-gex-GRCm39-2024-A",
    },
    "mRatBN7.2": {
        "fasta": "/data/ref_genomes/mRatBN7.2/src/Rattus_norvegicus.GRCr8.dna.toplevel.fa",
        "gtf": "/data/ref_genomes/mRatBN7.2/src/Rattus_norvegicus.GRCr8.115.gtf",
        "star_index": "/data/ref_genomes/mRatBN7.2/indices/star",
        "cellranger_index": "/data/shared/10xGenomics/refs/refdata-gex-mRatBN7-2-2024-A",
    },
    "Sscrofa11.1": {
        "fasta": "/data/ref_genomes/Sscrofa11.1/src/Sus_scrofa.Sscrofa11.1.dna.toplevel.fa",
        "gtf": "/data/ref_genomes/Sscrofa11.1/src/Sus_scrofa.Sscrofa11.1.115.gtf",
        "star_index": "/data/ref_genomes/Sscrofa11.1/indices/star",
        "cellranger_index": "",
    },
    "GRCz11": {
        "fasta": "/data/ref_genomes/GRCz11/src/Danio_rerio.GRCz11.dna.toplevel.fa",
        "gtf": "/data/ref_genomes/GRCz11/src/Danio_rerio.GRCz11.115.gtf",
        "star_index": "/data/ref_genomes/GRCz11/indices/star",
        "cellranger_index": "/data/shared/10xGenomics/refs/refdata-gex-GRCz11-ensembl115-2026-A",
    },
}


def supported_genome_labels() -> list[str]:
    return sorted(REFERENCE_MAP)


def parser_epilog() -> str:
    lines = [
        "Supported genome labels:",
        *[f"  - {label}" for label in supported_genome_labels()],
        "",
        "Supported aligners:",
        "  - cellranger",
        "  - star",
        "",
        "Runtime values are supplied by the rendered Linkar launcher via environment variables.",
        "Common overrides and inputs:",
        "  - SAMPLESHEET",
        "  - GENOME",
        "  - ALIGNER",
        "  - PROTOCOL",
        "  - STAR_INDEX",
        "  - CELLRANGER_INDEX",
        "  - EXPECTED_CELLS",
        "  - SKIP_CELLBENDER",
        "  - MAX_CPUS",
        "  - MAX_MEMORY",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve and run nf-core/scrnaseq for izkf_pack.",
        epilog=parser_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--render-only", action="store_true", help="Write the resolved run.sh and exit.")
    parser.add_argument("--run-script", default="resolved_run.sh", help="Path to the generated rerunnable shell script.")
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"[error] required environment variable is missing: {name}")
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_flag(name: str) -> bool:
    return optional_env(name).lower() in {"1", "true", "yes", "on"}


def normalize_memory(value: str) -> str:
    memory = value.strip()
    if memory.upper().endswith("GB"):
        return f"{memory[:-2]}.GB"
    return memory


def relative_path_for_command(base_dir: Path, target: Path) -> str:
    return os.path.relpath(target, start=base_dir)


def normalize_protocol(aligner: str, protocol: str) -> str:
    normalized = protocol.strip()
    if aligner == "cellranger":
        return normalized or DEFAULT_CELLRANGER_PROTOCOL
    if not normalized:
        raise SystemExit("[error] protocol is required when aligner is not cellranger.")
    if normalized.lower() == "auto":
        raise SystemExit("[error] protocol=auto is only supported when aligner=cellranger.")
    return normalized


def validate_aligner(aligner: str) -> str:
    normalized = aligner.strip().lower()
    if normalized not in SUPPORTED_ALIGNERS:
        supported = ", ".join(sorted(SUPPORTED_ALIGNERS))
        raise SystemExit(f"[error] unsupported aligner '{aligner}'. Supported values in izkf_pack are: {supported}.")
    return normalized


def resolve_path_override(value: str, *, ignore_roots: tuple[Path, ...] = ()) -> Path | None:
    if not value.strip():
        return None
    resolved = Path(value).expanduser().resolve()
    if any(resolved == root for root in ignore_roots):
        return None
    return resolved


def verify_existing(path: Path, *, label: str) -> Path:
    if not path.exists():
        raise SystemExit(f"[error] {label} was not found: {path}")
    return path


def resolve_references(
    genome: str,
    *,
    aligner: str,
    star_index: str,
    cellranger_index: str,
    allow_placeholders: bool = False,
    ignore_override_roots: tuple[Path, ...] = (),
) -> dict[str, Path | None]:
    if genome == GENOME_PLACEHOLDER:
        if allow_placeholders:
            override_star = resolve_path_override(star_index, ignore_roots=ignore_override_roots)
            override_cellranger = resolve_path_override(cellranger_index, ignore_roots=ignore_override_roots)
            return {
                "fasta": Path(FASTA_PLACEHOLDER),
                "gtf": Path(GTF_PLACEHOLDER),
                "star_index": (
                    verify_existing(override_star, label="STAR index override")
                    if override_star is not None
                    else Path(STAR_INDEX_PLACEHOLDER) if aligner == "star" else None
                ),
                "cellranger_index": (
                    verify_existing(override_cellranger, label="Cell Ranger reference override")
                    if override_cellranger is not None
                    else Path(CELLRANGER_INDEX_PLACEHOLDER) if aligner == "cellranger" else None
                ),
            }
        raise SystemExit(
            f"[error] genome is unresolved. Edit run.sh and replace {GENOME_PLACEHOLDER} with a supported genome before running."
        )
    spec = REFERENCE_MAP.get(genome)
    if spec is None:
        supported = ", ".join(supported_genome_labels())
        raise SystemExit(f"[error] unsupported genome '{genome}'. Supported genomes in izkf_pack are: {supported}.")

    resolved = {
        "fasta": verify_existing(Path(spec["fasta"]), label="reference FASTA"),
        "gtf": verify_existing(Path(spec["gtf"]), label="reference GTF"),
        "star_index": None,
        "cellranger_index": None,
    }

    override_star = resolve_path_override(star_index, ignore_roots=ignore_override_roots)
    if override_star is not None:
        resolved["star_index"] = verify_existing(override_star, label="STAR index override")
    elif spec.get("star_index"):
        candidate = Path(str(spec["star_index"]))
        if candidate.exists():
            resolved["star_index"] = candidate

    override_cellranger = resolve_path_override(cellranger_index, ignore_roots=ignore_override_roots)
    if override_cellranger is not None:
        resolved["cellranger_index"] = verify_existing(override_cellranger, label="Cell Ranger reference override")
    elif spec.get("cellranger_index"):
        candidate = Path(str(spec["cellranger_index"]))
        if candidate.exists():
            resolved["cellranger_index"] = candidate

    if aligner == "cellranger" and resolved["cellranger_index"] is None:
        raise SystemExit(
            "[error] cellranger_index is required for aligner=cellranger when no shared facility Cell Ranger reference is available for the selected genome."
        )

    return resolved


def stage_samplesheet(src: Path, dest: Path, *, expected_cells: str) -> None:
    with src.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        required = {"sample", "fastq_1", "fastq_2"}
        missing = sorted(required.difference(fieldnames))
        if missing:
            raise SystemExit(f"[error] samplesheet is missing required columns: {', '.join(missing)}")
        rows = list(reader)

    if not rows:
        raise SystemExit(f"[error] samplesheet contains no rows: {src}")

    if expected_cells:
        if "expected_cells" not in fieldnames:
            fieldnames.append("expected_cells")
        for row in rows:
            if not str(row.get("expected_cells", "")).strip():
                row["expected_cells"] = expected_cells

    with dest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return '""'
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def write_params_file(path: Path, params: dict[str, object]) -> None:
    lines = [f"{key}: {yaml_scalar(value)}" for key, value in params.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cli_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_runtime_nextflow_config(
    template_path: Path,
    output_path: Path,
    *,
    max_cpus: str,
    max_memory: str,
) -> None:
    text = template_path.read_text(encoding="utf-8")
    if max_cpus:
        text = text.replace("__EDIT_ME_MAX_CPUS__", str(int(max_cpus)))
    else:
        text = text.replace("        cpus: __EDIT_ME_MAX_CPUS__,\n", "")

    if max_memory:
        text = text.replace("__EDIT_ME_MAX_MEMORY__", normalize_memory(max_memory))
    else:
        text = text.replace("        memory: '__EDIT_ME_MAX_MEMORY__'\n", "")

    output_path.write_text(text, encoding="utf-8")


def run_version_command(command: list[str]) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        return {
            "command": " ".join(shlex.quote(part) for part in command),
            "source": "command",
            "error": str(exc),
        }
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return {
        "version": output.splitlines()[0] if output else "",
        "raw": output,
        "command": " ".join(shlex.quote(part) for part in command),
        "source": "command",
        "returncode": completed.returncode,
    }


def write_software_versions(
    output_path: Path,
    *,
    genome: str,
    aligner: str,
    protocol: str,
    skip_cellbender: bool,
    reference_summary: str,
) -> None:
    payload = {
        "software": [
            {"name": "nextflow", **run_version_command(["pixi", "run", "nextflow", "-version"])},
            {"name": PIPELINE_NAME, "version": PIPELINE_VERSION, "source": "static"},
            {"name": "execution_profile", "version": EXECUTION_PROFILE, "source": "static"},
            {"name": "genome", "version": genome, "source": "param"},
            {"name": "aligner", "version": aligner, "source": "param"},
            {"name": "protocol", "version": protocol, "source": "param"},
            {"name": "skip_cellbender", "version": str(skip_cellbender).lower(), "source": "param"},
            {"name": "reference", "version": reference_summary, "source": "param"},
        ]
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_nextflow_command(
    *,
    nextflow_config: Path,
    params: dict[str, object],
    resume: bool,
) -> list[str]:
    command = [
        "pixi",
        "run",
        "nextflow",
        "run",
        PIPELINE_NAME,
        "-r",
        PIPELINE_VERSION,
        "-profile",
        EXECUTION_PROFILE,
        "-c",
        str(nextflow_config),
    ]
    for key, value in params.items():
        command.extend([f"--{key}", cli_scalar(value)])
    if resume:
        command.append("-resume")
    return command


def format_shell_command_lines(command: list[str]) -> list[str]:
    lines: list[str] = []
    index = 0
    leading_parts: list[str] = []
    while index < len(command) and not command[index].startswith("-"):
        leading_parts.append(shlex.quote(command[index]))
        index += 1
    if leading_parts:
        lines.append(" ".join(leading_parts))
    while index < len(command):
        token = command[index]
        rendered = shlex.quote(token)
        if token.startswith("-") and index + 1 < len(command):
            next_token = command[index + 1]
            if not next_token.startswith("-"):
                rendered = f"{rendered} {shlex.quote(next_token)}"
                index += 1
        lines.append(rendered)
        index += 1
    return lines


def write_resolved_run_script(
    output_path: Path,
    *,
    command: list[str],
    guard_unresolved_params: bool,
) -> None:
    command_lines = format_shell_command_lines(command)
    command_text = " \\\n".join(command_lines)
    guard = ""
    if guard_unresolved_params:
        guard = (
            'if grep -q "__EDIT_ME_" "${script_dir}/params.yaml"; then\n'
            '  echo "[error] unresolved placeholders detected in params.yaml." >&2\n'
            '  echo "[error] rerender with --genome or --agendo-id, or edit the generated parameters before execution." >&2\n'
            "  exit 1\n"
            "fi\n\n"
        )
    script = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        'script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'cd "${script_dir}"\n\n'
        f"{guard}"
        "# Install the template-local environment before launching Nextflow.\n"
        "pixi install\n\n"
        'echo "[info] running"\n\n'
        f"{command_text}\n"
    )
    output_path.write_text(script, encoding="utf-8")
    output_path.chmod(0o755)


def write_runtime_command(
    output_path: Path,
    *,
    command: list[str],
    genome: str,
    aligner: str,
    protocol: str,
    expected_cells: str,
    skip_cellbender: bool,
    max_cpus: str,
    max_memory: str,
    reference_summary: str,
    params_file: Path,
    nextflow_config: Path,
    software_versions: Path,
    run_script: Path,
) -> None:
    payload = {
        "template": "nfcore_scrnaseq",
        "engine": "nextflow",
        "pipeline": PIPELINE_NAME,
        "pipeline_version": PIPELINE_VERSION,
        "command": command,
        "command_pretty": " ".join(shlex.quote(part) for part in command),
        "params": {
            "genome": genome,
            "aligner": aligner,
            "protocol": protocol,
            "expected_cells": expected_cells,
            "skip_cellbender": skip_cellbender,
            "max_cpus": max_cpus,
            "max_memory": max_memory,
            "reference": reference_summary,
        },
        "artifacts": {
            "params_file": str(params_file),
            "nextflow_config": str(nextflow_config),
            "software_versions": str(software_versions),
            "run_script": str(run_script),
        },
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def score_matrix_candidate(path: Path) -> tuple[int, int, str]:
    name = path.name
    if name == "combined_cellbender_filter_matrix.h5ad":
        return (0, 0, name)
    if name == "combined_emptydrops_filter_matrix.h5ad":
        return (0, 1, name)
    if name == "combined_filtered_matrix.h5ad":
        return (1, 0, name)
    if name == "combined_raw_matrix.h5ad":
        return (2, 0, name)
    if name.startswith("combined_") and name.endswith(".h5ad"):
        return (3, 0, name)
    if name.endswith("_cellbender_filter_matrix.h5ad"):
        return (4, 0, name)
    if name.endswith("_emptydrops_filter_matrix.h5ad"):
        return (4, 1, name)
    if name.endswith("_filtered_matrix.h5ad"):
        return (5, 0, name)
    if name.endswith("_raw_matrix.h5ad"):
        return (6, 0, name)
    return (7, 0, name)


def select_matrix_output(*, workspace_dir: Path, results_dir: Path, aligner: str) -> None:
    candidates = sorted((results_dir / aligner / "mtx_conversions").glob("*.h5ad"))
    selected = min(candidates, key=score_matrix_candidate) if candidates else None
    link_path = workspace_dir / "selected_matrix.h5ad"
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    if selected is not None:
        os.symlink(relative_path_for_command(workspace_dir, selected), link_path)
    payload = {
        "aligner": aligner,
        "selected": str(selected) if selected is not None else "",
        "selected_link": str(link_path) if selected is not None else "",
        "candidates": [str(path) for path in candidates],
    }
    (results_dir / "matrix_selection.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_script_path = Path(args.run_script).resolve()
    run_workspace_dir = run_script_path.parent
    run_workspace_dir.mkdir(parents=True, exist_ok=True)

    aligner = validate_aligner(require_env("ALIGNER"))
    protocol = normalize_protocol(aligner, optional_env("PROTOCOL"))
    genome = require_env("GENOME")
    results_dir = Path(require_env("LINKAR_RESULTS_DIR")).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    expected_cells = optional_env("EXPECTED_CELLS")
    skip_cellbender = optional_env("SKIP_CELLBENDER", "true").lower() == "true"
    max_cpus = optional_env("MAX_CPUS")
    max_memory = optional_env("MAX_MEMORY")
    resume = env_flag("LINKAR_NEXTFLOW_RESUME")
    star_index_override = optional_env("STAR_INDEX")
    cellranger_index_override = optional_env("CELLRANGER_INDEX")
    ignore_override_roots = tuple(
        Path(path).expanduser().resolve()
        for path in (
            optional_env("LINKAR_PROJECT_DIR"),
            str(run_workspace_dir),
        )
        if path
    )
    star_index_override_path = resolve_path_override(star_index_override, ignore_roots=ignore_override_roots)
    cellranger_index_override_path = resolve_path_override(
        cellranger_index_override,
        ignore_roots=ignore_override_roots,
    )

    references = resolve_references(
        genome,
        aligner=aligner,
        star_index=str(star_index_override_path) if star_index_override_path is not None else "",
        cellranger_index=str(cellranger_index_override_path) if cellranger_index_override_path is not None else "",
        allow_placeholders=args.render_only,
        ignore_override_roots=ignore_override_roots,
    )
    reference_summary = (
        references["cellranger_index"].name if aligner == "cellranger" and references["cellranger_index"] is not None
        else genome
    )

    staged_samplesheet = run_workspace_dir / "samplesheet.csv"
    stage_samplesheet(Path(require_env("SAMPLESHEET")).resolve(), staged_samplesheet, expected_cells=expected_cells)

    params_file = run_workspace_dir / "params.yaml"
    params_payload: dict[str, object] = {
        "input": relative_path_for_command(run_workspace_dir, staged_samplesheet),
        "outdir": relative_path_for_command(run_workspace_dir, results_dir),
        "aligner": aligner,
        "protocol": protocol,
        "genome": genome,
        "igenomes_ignore": True,
        "fasta": str(references["fasta"]),
        "gtf": str(references["gtf"]),
    }
    if skip_cellbender:
        params_payload["skip_cellbender"] = True
    if aligner == "star" and references["star_index"] is not None:
        params_payload["star_index"] = str(references["star_index"])
    if aligner == "cellranger" and references["cellranger_index"] is not None:
        params_payload["cellranger_index"] = str(references["cellranger_index"])
    write_params_file(params_file, params_payload)

    command_params: dict[str, object] = {
        "input": relative_path_for_command(run_workspace_dir, staged_samplesheet),
        "outdir": relative_path_for_command(run_workspace_dir, results_dir),
        "aligner": aligner,
        "protocol": protocol,
        "genome": genome,
        "igenomes_ignore": True,
    }
    if skip_cellbender:
        command_params["skip_cellbender"] = True
    if genome == GENOME_PLACEHOLDER:
        command_params["fasta"] = str(references["fasta"])
        command_params["gtf"] = str(references["gtf"])
        if aligner == "star" and references["star_index"] is not None:
            command_params["star_index"] = str(references["star_index"])
        if aligner == "cellranger" and references["cellranger_index"] is not None:
            command_params["cellranger_index"] = str(references["cellranger_index"])
    else:
        if star_index_override_path is not None and aligner == "star" and references["star_index"] is not None:
            command_params["star_index"] = str(references["star_index"])
        if cellranger_index_override_path is not None and aligner == "cellranger" and references["cellranger_index"] is not None:
            command_params["cellranger_index"] = str(references["cellranger_index"])

    nextflow_config_path = run_workspace_dir / "nextflow.config"
    write_runtime_nextflow_config(
        Path(__file__).resolve().with_name("nextflow.config"),
        nextflow_config_path,
        max_cpus=max_cpus,
        max_memory=max_memory,
    )

    command = build_nextflow_command(
        nextflow_config=Path(relative_path_for_command(run_workspace_dir, nextflow_config_path)),
        params=command_params,
        resume=resume,
    )
    write_resolved_run_script(
        run_script_path,
        command=command,
        guard_unresolved_params=args.render_only and genome == GENOME_PLACEHOLDER,
    )

    software_versions_path = results_dir / "software_versions.json"
    write_software_versions(
        software_versions_path,
        genome=genome,
        aligner=aligner,
        protocol=protocol,
        skip_cellbender=skip_cellbender,
        reference_summary=reference_summary,
    )
    write_runtime_command(
        results_dir / "runtime_command.json",
        command=command,
        genome=genome,
        aligner=aligner,
        protocol=protocol,
        expected_cells=expected_cells,
        skip_cellbender=skip_cellbender,
        max_cpus=max_cpus,
        max_memory=max_memory,
        reference_summary=reference_summary,
        params_file=params_file,
        nextflow_config=nextflow_config_path,
        software_versions=software_versions_path,
        run_script=run_script_path,
    )

    if args.render_only:
        return 0

    subprocess.run(
        [str(run_script_path), *(["-resume"] if resume else [])],
        check=True,
        cwd=run_workspace_dir,
    )
    select_matrix_output(workspace_dir=run_workspace_dir, results_dir=results_dir, aligner=aligner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
