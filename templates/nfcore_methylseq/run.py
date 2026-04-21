#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path


PIPELINE_NAME = "nf-core/methylseq"
PIPELINE_VERSION = "4.2.0"
EXECUTION_PROFILE = "docker"
GENOME_PLACEHOLDER = "__EDIT_ME_GENOME__"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"[error] required environment variable is missing: {name}")
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_flag(name: str) -> bool:
    return optional_env(name).lower() in {"1", "true", "yes", "on"}


def project_title() -> str:
    explicit = optional_env("PROJECT_NAME")
    if explicit:
        return explicit
    project_dir = optional_env("LINKAR_PROJECT_DIR")
    if project_dir:
        return Path(project_dir).name
    return Path.cwd().name


def normalize_memory(value: str) -> str:
    memory = value.strip()
    if memory.upper().endswith("GB"):
        return f"{memory[:-2]}.GB"
    return memory


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
    rrbs: bool,
) -> None:
    payload = {
        "software": [
            {"name": "nextflow", **run_version_command(["pixi", "run", "nextflow", "-version"])},
            {"name": PIPELINE_NAME, "version": PIPELINE_VERSION, "source": "static"},
            {"name": "execution_profile", "version": EXECUTION_PROFILE, "source": "static"},
            {"name": "genome", "version": genome, "source": "param"},
            {"name": "rrbs", "version": str(rrbs).lower(), "source": "param"},
        ]
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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
        text = text.replace("    cpus: __EDIT_ME_MAX_CPUS__,\n", "")

    if max_memory:
        text = text.replace("__EDIT_ME_MAX_MEMORY__", normalize_memory(max_memory))
    else:
        text = text.replace("    memory: '__EDIT_ME_MAX_MEMORY__'\n", "")

    output_path.write_text(text, encoding="utf-8")


def build_nextflow_command(
    *,
    nextflow_config: Path,
    samplesheet: str,
    results_dir: str,
    genome: str,
    multiqc_title: str,
    rrbs: bool,
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
        "--input",
        samplesheet,
        "--outdir",
        results_dir,
        "--genome",
        genome,
        "--multiqc_title",
        multiqc_title,
    ]
    if rrbs:
        command.append("--rrbs")
    if resume:
        command.append("-resume")
    return command


def write_runtime_command(
    output_path: Path,
    *,
    command: list[str],
    genome: str,
    rrbs: bool,
    project_name: str,
    resume: bool,
    max_cpus: str,
    max_memory: str,
    nextflow_config: Path,
    software_versions: Path,
) -> None:
    payload = {
        "template": "nfcore_methylseq",
        "engine": "nextflow",
        "pipeline": PIPELINE_NAME,
        "pipeline_version": PIPELINE_VERSION,
        "command": command,
        "command_pretty": " ".join(shlex.quote(part) for part in command),
        "params": {
            "genome": genome,
            "rrbs": rrbs,
            "project_name": project_name,
            "resume": resume,
            "max_cpus": max_cpus,
            "max_memory": max_memory,
        },
        "artifacts": {
            "nextflow_config": str(nextflow_config),
            "software_versions": str(software_versions),
        },
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def detect_run_name(log_path: Path) -> str:
    if not log_path.exists():
        return ""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"Run name:\s+(\S+)", text)
    return matches[-1] if matches else ""


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    genome = require_env("GENOME")
    if genome == GENOME_PLACEHOLDER:
        raise SystemExit(
            f"[error] genome is unresolved. Edit run.sh and replace {GENOME_PLACEHOLDER} with a supported genome before running."
        )

    results_dir = Path(require_env("LINKAR_RESULTS_DIR")).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    samplesheet = str(Path(require_env("SAMPLESHEET")).resolve())
    rrbs = optional_env("RRBS", "true").lower() == "true"
    title = project_title()
    resume = env_flag("LINKAR_NEXTFLOW_RESUME")
    max_cpus = optional_env("MAX_CPUS")
    max_memory = optional_env("MAX_MEMORY")

    print(
        f"[info] {PIPELINE_NAME} profile={EXECUTION_PROFILE} genome={genome} rrbs={str(rrbs).lower()} resume={str(resume).lower()}",
        flush=True,
    )

    subprocess.run(["pixi", "install"], check=True)
    subprocess.run(["pixi", "run", "nextflow", "-version"], check=False)

    software_versions_path = results_dir / "software_versions.json"
    write_software_versions(software_versions_path, genome=genome, rrbs=rrbs)

    runtime_nextflow_config = results_dir / "nextflow.config"
    write_runtime_nextflow_config(
        script_dir / "nextflow.config",
        runtime_nextflow_config,
        max_cpus=max_cpus,
        max_memory=max_memory,
    )

    command = build_nextflow_command(
        nextflow_config=runtime_nextflow_config,
        samplesheet=samplesheet,
        results_dir=str(results_dir),
        genome=genome,
        multiqc_title=title,
        rrbs=rrbs,
        resume=resume,
    )
    write_runtime_command(
        results_dir / "runtime_command.json",
        command=command,
        genome=genome,
        rrbs=rrbs,
        project_name=title,
        resume=resume,
        max_cpus=max_cpus,
        max_memory=max_memory,
        nextflow_config=runtime_nextflow_config,
        software_versions=software_versions_path,
    )

    subprocess.run(command, check=True, cwd=results_dir)

    run_name = detect_run_name(Path(".nextflow.log"))
    if run_name:
        subprocess.run(["pixi", "run", "nextflow", "clean", run_name, "-f"], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
