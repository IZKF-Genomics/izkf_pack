#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path


PIPELINE_NAME = "nf-core/rnaseq"
PIPELINE_VERSION = "3.22.2"
EXECUTION_PROFILE = "docker"
GENOME_PLACEHOLDER = "__EDIT_ME_GENOME__"
UMI_KIT = "UMI Second Strand SynthesisModule for QuantSeq FWD"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve and run nf-core/rnaseq for 3' mRNA-seq.")
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


def effective_genome(genome: str, spikein: str) -> str:
    if spikein and "ERCC" in spikein:
        return f"{genome}_with_ERCC"
    return genome


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
    umi: str,
    spikein: str,
) -> None:
    payload = {
        "software": [
            {"name": "nextflow", **run_version_command(["pixi", "run", "nextflow", "-version"])},
            {"name": PIPELINE_NAME, "version": PIPELINE_VERSION, "source": "static"},
            {"name": "execution_profile", "version": EXECUTION_PROFILE, "source": "static"},
            {"name": "genome", "version": genome, "source": "param"},
            {"name": "umi", "version": umi or "none", "source": "param"},
            {"name": "spikein", "version": spikein or "none", "source": "param"},
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
        text = text.replace("        cpus: __EDIT_ME_MAX_CPUS__,\n", "")

    if max_memory:
        text = text.replace("__EDIT_ME_MAX_MEMORY__", normalize_memory(max_memory))
    else:
        text = text.replace("        memory: '__EDIT_ME_MAX_MEMORY__'\n", "")

    output_path.write_text(text, encoding="utf-8")


def build_nextflow_command(
    *,
    nextflow_config: Path,
    samplesheet: str,
    results_dir: str,
    genome: str,
    umi: str,
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
        "--extra_salmon_quant_args=--noLengthCorrection",
        "--extra_star_align_args=--alignIntronMax 1000000 --alignIntronMin 20 --alignMatesGapMax 1000000 --alignSJoverhangMin 8 --outFilterMismatchNmax 999 --outFilterMultimapNmax 20 --outFilterType BySJout --outFilterMismatchNoverLmax 0.1 --clip3pAdapterSeq AAAAAAAA",
        "--genome",
        genome,
        "--igenomes_ignore",
        "true",
        "--igenomes_base",
        "/data/shared/igenomes/",
        "--gencode",
        "--featurecounts_group_type",
        "gene_type",
    ]
    if resume:
        command.append("-resume")
    if umi == UMI_KIT:
        command.extend(
            [
                "--with_umi",
                "--umitools_extract_method",
                "regex",
                "--umitools_bc_pattern",
                "^(?P<umi_1>.{8})(?P<discard_1>.{6}).*",
            ]
        )
    return command


def write_resolved_run_script(
    output_path: Path,
    *,
    command: list[str],
) -> None:
    quoted_parts = "\n".join(f"  {json.dumps(part)}" for part in command)
    script = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        'script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        "resume_requested=false\n\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        "    -resume)\n"
        "      resume_requested=true\n"
        "      ;;\n"
        "    -h|--help)\n"
        '      echo "Usage: ./run.sh [-resume]"\n'
        "      exit 0\n"
        "      ;;\n"
        "    *)\n"
        '      echo "[error] unsupported argument: ${arg}" >&2\n'
        '      echo "Usage: ./run.sh [-resume]" >&2\n'
        "      exit 2\n"
        "      ;;\n"
        "  esac\n"
        "done\n\n"
        'cd "${script_dir}"\n\n'
        "# Install the template-local environment before launching Nextflow.\n"
        "pixi install\n\n"
        "command=(\n"
        f"{quoted_parts}\n"
        ")\n\n"
        'if [[ "${resume_requested}" == "true" ]]; then\n'
        '  command+=("-resume")\n'
        "fi\n\n"
        'printf "[info] running:"\n'
        'printf " %q" "${command[@]}"\n'
        'printf "\\n"\n'
        '"${command[@]}"\n'
    )
    output_path.write_text(script, encoding="utf-8")
    output_path.chmod(0o755)


def write_runtime_command(
    output_path: Path,
    *,
    command: list[str],
    genome: str,
    raw_genome: str,
    umi: str,
    spikein: str,
    resume: bool,
    max_cpus: str,
    max_memory: str,
    nextflow_config: Path,
    software_versions: Path,
    run_script: Path,
) -> None:
    payload = {
        "template": "nfcore_3mrnaseq",
        "engine": "nextflow",
        "pipeline": PIPELINE_NAME,
        "pipeline_version": PIPELINE_VERSION,
        "command": command,
        "command_pretty": " ".join(shlex.quote(part) for part in command),
        "params": {
            "genome": raw_genome,
            "effective_genome": genome,
            "umi": umi,
            "spikein": spikein,
            "resume": resume,
            "max_cpus": max_cpus,
            "max_memory": max_memory,
        },
        "artifacts": {
            "nextflow_config": str(nextflow_config),
            "software_versions": str(software_versions),
            "run_script": str(run_script),
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
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    genome = require_env("GENOME")
    if genome == GENOME_PLACEHOLDER:
        raise SystemExit(
            f"[error] genome is unresolved. Edit run.sh and replace {GENOME_PLACEHOLDER} with a supported genome before running."
        )

    spikein = optional_env("SPIKEIN")
    umi = optional_env("UMI")
    chosen_genome = effective_genome(genome, spikein)
    results_dir = Path(require_env("LINKAR_RESULTS_DIR")).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    samplesheet = str(Path(require_env("SAMPLESHEET")).resolve())
    resume = env_flag("LINKAR_NEXTFLOW_RESUME")
    max_cpus = optional_env("MAX_CPUS")
    max_memory = optional_env("MAX_MEMORY")

    print(
        f"[info] {PIPELINE_NAME} profile={EXECUTION_PROFILE} genome={chosen_genome} resume={str(resume).lower()}",
        flush=True,
    )

    subprocess.run(["pixi", "install"], check=True)
    subprocess.run(["pixi", "run", "nextflow", "-version"], check=False)

    software_versions_path = results_dir / "software_versions.json"
    write_software_versions(
        software_versions_path,
        genome=chosen_genome,
        umi=umi,
        spikein=spikein,
    )

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
        genome=chosen_genome,
        umi=umi,
        resume=False,
    )
    resolved_run_script = Path(args.run_script)
    if not resolved_run_script.is_absolute():
        resolved_run_script = (script_dir / resolved_run_script).resolve()
    write_resolved_run_script(
        resolved_run_script,
        command=command,
    )
    write_runtime_command(
        results_dir / "runtime_command.json",
        command=command,
        genome=chosen_genome,
        raw_genome=genome,
        umi=umi,
        spikein=spikein,
        resume=resume,
        max_cpus=max_cpus,
        max_memory=max_memory,
        nextflow_config=runtime_nextflow_config,
        software_versions=software_versions_path,
        run_script=resolved_run_script,
    )
    if args.render_only:
        print(f"[info] wrote {resolved_run_script}", flush=True)
        return 0

    run_script_command = ["bash", str(resolved_run_script)]
    if resume:
        run_script_command.append("-resume")
    subprocess.run(run_script_command, check=True, cwd=script_dir)

    run_name = detect_run_name(results_dir / ".nextflow.log")
    if run_name:
        subprocess.run(["pixi", "run", "nextflow", "clean", run_name, "-f"], check=False, cwd=results_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
