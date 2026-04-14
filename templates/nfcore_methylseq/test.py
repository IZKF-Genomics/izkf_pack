#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent
FUNCTIONS_DIR = TEMPLATE_DIR.parent.parent / "functions"


def load_function(name: str):
    path = FUNCTIONS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load function module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve


def make_fake_runtime_bin(root: Path) -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    nextflow = bin_dir / "nextflow"
    nextflow.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == \"-version\" ]]; then\n"
        "  echo 'nextflow version 24.10.0'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == \"run\" ]]; then\n"
        "  printf '%s\\n' \"$*\" > \"${NFCORE_ARGS_LOG:?}\"\n"
        "  outdir=''\n"
        "  for ((i=1; i<=$#; i++)); do\n"
        "    if [[ \"${!i}\" == \"--outdir\" ]]; then\n"
        "      j=$((i+1))\n"
        "      outdir=\"${!j}\"\n"
        "    fi\n"
        "  done\n"
        "  mkdir -p \"${outdir}/multiqc\" \"${outdir}/pipeline_info\"\n"
        "  printf '<html>multiqc</html>\\n' > \"${outdir}/multiqc/multiqc_report.html\"\n"
        "  printf 'trace\\n' > \"${outdir}/pipeline_info/execution_trace.txt\"\n"
        "  printf 'Run name: methylseq-test-run\\n' > .nextflow.log\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == \"clean\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unsupported fake nextflow invocation: $*\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    nextflow.chmod(0o755)
    pixi = bin_dir / "pixi"
    pixi.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == \"install\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == \"run\" && \"${2:-}\" == \"nextflow\" ]]; then\n"
        "  shift 2\n"
        f"exec {str(nextflow)} \"$@\"\n"
        "fi\n"
        "echo \"unsupported fake pixi invocation: $*\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    pixi.chmod(0o755)
    docker = bin_dir / "docker"
    docker.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    docker.chmod(0o755)
    return bin_dir


def test_rendered_run_script() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-methylseq-test-") as tmp:
        tmpdir = Path(tmp)
        fake_bin = make_fake_runtime_bin(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text(
            "sample,fastq_1,fastq_2,genome\nS1,R1.fastq.gz,R2.fastq.gz,\n",
            encoding="utf-8",
        )
        results_dir = tmpdir / "results"
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["NFCORE_ARGS_LOG"] = str(tmpdir / "args.log")
        env["LINKAR_RESULTS_DIR"] = str(results_dir)
        env["LINKAR_PROJECT_DIR"] = str(tmpdir / "rrbs_project")
        env["SAMPLESHEET"] = str(samplesheet)
        env["GENOME"] = "GRCm39"
        env["RRBS"] = "true"
        env["PROJECT_NAME"] = "rrbs_project"
        env["MAX_CPUS"] = "12"
        env["MAX_MEMORY"] = "48GB"
        completed = subprocess.run(
            ["python3", str(TEMPLATE_DIR / "run.py")],
            cwd=tmpdir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        args_text = (tmpdir / "args.log").read_text(encoding="utf-8")
        assert "nf-core/methylseq" in args_text
        assert "-profile docker" in args_text
        assert f"-c {results_dir / 'resource_limits.config'}" in args_text
        assert "--rrbs" in args_text
        assert "--multiqc_title rrbs_project" in args_text
        assert "--genome GRCm39" in args_text
        assert "--max_cpus" not in args_text
        assert "--max_memory" not in args_text
        assert "gpu" not in args_text
        assert (results_dir / "multiqc" / "multiqc_report.html").exists()
        assert (results_dir / "pipeline_info" / "execution_trace.txt").exists()
        limits_text = (results_dir / "resource_limits.config").read_text(encoding="utf-8")
        assert "cpus: 12" in limits_text
        assert "memory: '48.GB'" in limits_text
        runtime_payload = json.loads((results_dir / "runtime_command.json").read_text(encoding="utf-8"))
        assert runtime_payload["template"] == "nfcore_methylseq"
        assert runtime_payload["engine"] == "nextflow"
        assert runtime_payload["pipeline"] == "nf-core/methylseq"
        assert runtime_payload["pipeline_version"] == "4.2.0"
        assert runtime_payload["command"][:4] == ["pixi", "run", "nextflow", "run"]
        assert "--rrbs" in runtime_payload["command"]
        assert runtime_payload["params"]["genome"] == "GRCm39"
        assert runtime_payload["params"]["rrbs"] is True
        assert runtime_payload["params"]["project_name"] == "rrbs_project"
        assert runtime_payload["params"]["max_cpus"] == "12"
        assert runtime_payload["params"]["max_memory"] == "48GB"
        assert runtime_payload["artifacts"]["resource_limits_config"] == str(results_dir / "resource_limits.config")
        assert runtime_payload["artifacts"]["software_versions"] == str(results_dir / "software_versions.json")
        assert "pixi run nextflow run nf-core/methylseq" in runtime_payload["command_pretty"]
        versions_payload = json.loads((results_dir / "software_versions.json").read_text(encoding="utf-8"))
        versions = {entry["name"]: entry for entry in versions_payload["software"]}
        assert versions["nextflow"]["version"] == "nextflow version 24.10.0"
        assert versions["nf-core/methylseq"]["version"] == "4.2.0"
        assert versions["execution_profile"]["version"] == "docker"
        assert versions["genome"]["version"] == "GRCm39"
        assert versions["rrbs"]["version"] == "true"


class FakeProject:
    def __init__(self, fastq_files: list[str]) -> None:
        self.data = {
            "templates": [
                {
                    "id": "demultiplex",
                    "outputs": {"demux_fastq_files": fastq_files},
                }
            ]
        }


class FakeTemplate:
    root = TEMPLATE_DIR


class FakeContext:
    def __init__(self, fastq_files: list[str]) -> None:
        self.project = FakeProject(fastq_files)
        self.template = FakeTemplate()
        self.resolved_params = {}

    def latest_output(self, key: str, template_id: str | None = None):
        for entry in reversed(self.project.data["templates"]):
            if template_id is not None and entry["id"] != template_id:
                continue
            outputs = entry.get("outputs") or {}
            if key in outputs:
                return outputs[key]
        return None


def test_samplesheet_binding() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-methylseq-samplesheet-test-") as tmp:
        tmpdir = Path(tmp)
        fastq_dir = tmpdir / "demux-results" / "output"
        fastq_dir.mkdir(parents=True)
        sample_r1 = fastq_dir / "RRBS_A_S1_L001_R1_001.fastq.gz"
        sample_r2 = fastq_dir / "RRBS_A_S1_L001_R2_001.fastq.gz"
        undetermined = fastq_dir / "Undetermined_S0_R1_001.fastq.gz"
        sample_r1.write_text("r1\n", encoding="utf-8")
        sample_r2.write_text("r2\n", encoding="utf-8")
        undetermined.write_text("skip\n", encoding="utf-8")

        resolve = load_function("generate_nfcore_methylseq_samplesheet")
        output = Path(resolve(FakeContext([str(sample_r1), str(sample_r2), str(undetermined)])))
        assert output.exists()
        rows = list(csv.reader(output.open(encoding="utf-8")))
        assert rows[0] == ["sample", "fastq_1", "fastq_2", "genome"]
        assert rows[1][0] == "RRBS_A"
        assert rows[1][1] == str(sample_r1.resolve())
        assert rows[1][2] == str(sample_r2.resolve())
        assert rows[1][3] == ""


def main() -> None:
    test_rendered_run_script()
    test_samplesheet_binding()
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "entry: run.sh" in template_text
    assert "- pixi" in template_text
    assert "default: true" in template_text
    assert 'exec python3 "${script_dir}/run.py"' in run_sh_text
    assert 'subprocess.run(["pixi", "install"], check=True)' in run_py_text
    assert '["pixi", "run", "nextflow", "-version"]' in run_py_text
    assert 'runtime_command.json' in run_py_text
    assert 'command_pretty' in run_py_text
    assert 'resource_limits.config' in run_py_text
    assert 'path: runtime_command.json' in template_text
    assert 'if rrbs:' in run_py_text
    assert '"--multiqc_title"' in run_py_text
    assert 'write_software_versions' in run_py_text
    assert "nf-core/methylseq" in spec_text
    print("nfcore_methylseq template test passed")


if __name__ == "__main__":
    main()
