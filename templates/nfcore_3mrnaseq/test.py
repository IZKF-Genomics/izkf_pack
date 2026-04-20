#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
FUNCTIONS_DIR = TEMPLATE_DIR.parent.parent / "functions"
UMI_KIT = "UMI Second Strand SynthesisModule for QuantSeq FWD"


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
        "  mkdir -p \"${outdir}/multiqc\" \"${outdir}/salmon\" \"${outdir}/pipeline_info\"\n"
        "  printf '<html>multiqc</html>\\n' > \"${outdir}/multiqc/multiqc_report.html\"\n"
        "  printf 'quant\\n' > \"${outdir}/salmon/quant.sf\"\n"
        "  printf 'trace\\n' > \"${outdir}/pipeline_info/execution_trace.txt\"\n"
        "  printf 'Run name: rnaseq-test-run\\n' > .nextflow.log\n"
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
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-3mrnaseq-test-") as tmp:
        tmpdir = Path(tmp)
        fake_bin = make_fake_runtime_bin(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text(
            "sample,fastq_1,fastq_2,strandedness\nS1,R1.fastq.gz,R2.fastq.gz,forward\n",
            encoding="utf-8",
        )
        results_dir = tmpdir / "results"
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["NFCORE_ARGS_LOG"] = str(tmpdir / "args.log")
        env["LINKAR_RESULTS_DIR"] = str(results_dir)
        env["LINKAR_PROJECT_DIR"] = str(tmpdir / "threeprime_project")
        env["SAMPLESHEET"] = str(samplesheet)
        env["GENOME"] = "GRCh38"
        env["UMI"] = UMI_KIT
        env["SPIKEIN"] = "ERCC RNA Spike-in Mix"
        env["MAX_CPUS"] = "16"
        env["MAX_MEMORY"] = "64GB"
        rendered_run_script = tmpdir / "run.sh"
        completed = subprocess.run(
            ["python3", str(TEMPLATE_DIR / "run.py"), "--run-script", str(rendered_run_script)],
            cwd=tmpdir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        rendered_run_text = rendered_run_script.read_text(encoding="utf-8")
        assert "pixi install" in rendered_run_text
        assert "Usage: ./run.sh [-resume]" in rendered_run_text
        assert '"--with_umi"' in rendered_run_text
        assert '"--umitools_extract_method"' in rendered_run_text
        rerun = subprocess.run(
            ["bash", str(rendered_run_script), "-resume"],
            cwd=tmpdir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert rerun.returncode == 0, rerun.stderr
        args_text = (tmpdir / "args.log").read_text(encoding="utf-8")
        assert "nf-core/rnaseq" in args_text
        assert "-profile docker" in args_text
        assert f"-c {results_dir / 'nextflow.config'}" in args_text
        assert "--genome GRCh38_with_ERCC" in args_text
        assert "-resume" in args_text
        assert "--with_umi" in args_text
        assert "--umitools_extract_method regex" in args_text
        assert "--max_cpus" not in args_text
        assert "--max_memory" not in args_text
        assert (results_dir / "multiqc" / "multiqc_report.html").exists()
        assert (results_dir / "salmon" / "quant.sf").exists()
        nextflow_config_text = (results_dir / "nextflow.config").read_text(encoding="utf-8")
        assert "cpus: 16" in nextflow_config_text
        assert "memory: '64.GB'" in nextflow_config_text
        assert "__EDIT_ME_MAX_CPUS__" not in nextflow_config_text
        assert "__EDIT_ME_MAX_MEMORY__" not in nextflow_config_text
        runtime_payload = json.loads((results_dir / "runtime_command.json").read_text(encoding="utf-8"))
        assert runtime_payload["template"] == "nfcore_3mrnaseq"
        assert runtime_payload["engine"] == "nextflow"
        assert runtime_payload["pipeline"] == "nf-core/rnaseq"
        assert runtime_payload["pipeline_version"] == "3.22.2"
        assert runtime_payload["command"][:4] == ["pixi", "run", "nextflow", "run"]
        assert runtime_payload["params"]["genome"] == "GRCh38"
        assert runtime_payload["params"]["effective_genome"] == "GRCh38_with_ERCC"
        assert runtime_payload["params"]["umi"] == UMI_KIT
        assert runtime_payload["params"]["spikein"] == "ERCC RNA Spike-in Mix"
        assert runtime_payload["params"]["resume"] is False
        assert runtime_payload["params"]["max_cpus"] == "16"
        assert runtime_payload["params"]["max_memory"] == "64GB"
        assert runtime_payload["artifacts"]["nextflow_config"] == str(results_dir / "nextflow.config")
        assert runtime_payload["artifacts"]["software_versions"] == str(results_dir / "software_versions.json")
        assert runtime_payload["artifacts"]["run_script"] == str(rendered_run_script)
        versions_payload = json.loads((results_dir / "software_versions.json").read_text(encoding="utf-8"))
        versions = {entry["name"]: entry for entry in versions_payload["software"]}
        assert versions["nextflow"]["version"] == "nextflow version 24.10.0"
        assert versions["nf-core/rnaseq"]["version"] == "3.22.2"
        assert versions["execution_profile"]["version"] == "docker"
        assert versions["genome"]["version"] == "GRCh38_with_ERCC"
        assert versions["umi"]["version"] == UMI_KIT
        assert versions["spikein"]["version"] == "ERCC RNA Spike-in Mix"


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
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-samplesheet-test-") as tmp:
        tmpdir = Path(tmp)
        fastq_dir = tmpdir / "demux-results" / "output"
        fastq_dir.mkdir(parents=True)
        sample_r1 = fastq_dir / "SampleA_S1_R1_001.fastq.gz"
        sample_r2 = fastq_dir / "SampleA_S1_R2_001.fastq.gz"
        undetermined = fastq_dir / "Undetermined_S0_R1_001.fastq.gz"
        sample_r1.write_text("r1\n", encoding="utf-8")
        sample_r2.write_text("r2\n", encoding="utf-8")
        undetermined.write_text("skip\n", encoding="utf-8")

        resolve = load_function("generate_nfcore_rnaseq_samplesheet_forward")
        output = Path(resolve(FakeContext([str(sample_r1), str(sample_r2), str(undetermined)])))
        assert output.exists()
        rows = list(csv.reader(output.open(encoding="utf-8")))
        assert rows[0] == ["sample", "fastq_1", "fastq_2", "strandedness"]
        assert rows[1][0] == "SampleA"
        assert rows[1][3] == "forward"


def test_agendo_bindings_use_cached_metadata() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-agendo-test-") as tmp:
        tmpdir = Path(tmp)
        cache_dir = tmpdir / "agendo"
        cache_dir.mkdir(parents=True)
        (cache_dir / "12345.json").write_text(
            json.dumps(
                {
                    "organism": "human",
                    "umi": UMI_KIT,
                    "spike_in": "ERCC RNA Spike-in Mix",
                }
            ),
            encoding="utf-8",
        )

        class CachedContext:
            def __init__(self) -> None:
                self.resolved_params = {"agendo_id": "12345"}

        env_before = os.environ.get("LINKAR_HOME")
        os.environ["LINKAR_HOME"] = str(tmpdir)
        try:
            assert load_function("get_agendo_genome")(CachedContext()) == "GRCh38"
            assert load_function("get_agendo_umi")(CachedContext()) == UMI_KIT
            assert load_function("get_agendo_spikein")(CachedContext()) == "ERCC RNA Spike-in Mix"
        finally:
            if env_before is None:
                os.environ.pop("LINKAR_HOME", None)
            else:
                os.environ["LINKAR_HOME"] = env_before


def test_agendo_genome_unknown_organism_returns_placeholder() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-agendo-unknown-") as tmp:
        tmpdir = Path(tmp)
        cache_dir = tmpdir / "agendo"
        cache_dir.mkdir(parents=True)
        (cache_dir / "99999.json").write_text(
            json.dumps({"organism": "other"}),
            encoding="utf-8",
        )

        class CachedContext:
            def __init__(self) -> None:
                self.resolved_params = {"agendo_id": "99999"}
                self.warnings = []

            def warn(self, message: str, *, action: str | None = None, fallback=None) -> None:
                self.warnings.append(
                    {"message": message, "action": action, "fallback": fallback}
                )

        env_before = os.environ.get("LINKAR_HOME")
        os.environ["LINKAR_HOME"] = str(tmpdir)
        try:
            ctx = CachedContext()
            assert load_function("get_agendo_genome")(ctx) == "__EDIT_ME_GENOME__"
            assert ctx.warnings == [
                {
                    "message": "Could not derive genome from Agendo organism 'other'.",
                    "action": "Edit run.sh and replace __EDIT_ME_GENOME__ before execution.",
                    "fallback": "__EDIT_ME_GENOME__",
                }
            ]
        finally:
            if env_before is None:
                os.environ.pop("LINKAR_HOME", None)
            else:
                os.environ["LINKAR_HOME"] = env_before


def main() -> None:
    test_rendered_run_script()
    test_samplesheet_binding()
    test_agendo_bindings_use_cached_metadata()
    test_agendo_genome_unknown_organism_returns_placeholder()
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    nextflow_config_text = (TEMPLATE_DIR / "nextflow.config").read_text(encoding="utf-8")
    assert "python3 ./run.py --run-script ./run.sh" in template_text
    assert "python3 ./run.py --render-only --run-script ./run.sh" in template_text
    assert "- pixi" in template_text
    assert "- python3" in template_text
    assert 'resolved_run.sh' in run_sh_text
    assert 'LINKAR_NEXTFLOW_RESUME=true' in run_sh_text
    assert 'exec python3 "${script_dir}/run.py" --run-script "${script_dir}/resolved_run.sh"' in run_sh_text
    assert 'subprocess.run(["pixi", "install"], check=True)' in run_py_text
    assert 'pixi install' in run_py_text
    assert 'Usage: ./run.sh [-resume]' in run_py_text
    assert 'runtime_command.json' in run_py_text
    assert 'command_pretty' in run_py_text
    assert 'results_dir / "nextflow.config"' in run_py_text
    assert 'UMI Second Strand SynthesisModule for QuantSeq FWD' in run_py_text
    assert 'path: runtime_command.json' in template_text
    assert "__EDIT_ME_MAX_CPUS__" in nextflow_config_text
    assert "__EDIT_ME_MAX_MEMORY__" in nextflow_config_text
    pack_text = (TEMPLATE_DIR.parent.parent / "linkar_pack.yaml").read_text(encoding="utf-8")
    pack_data = yaml.safe_load(pack_text)
    nfcore_params = pack_data["templates"]["nfcore_3mrnaseq"]["params"]
    assert nfcore_params["umi"]["function"] == "get_agendo_umi"
    assert nfcore_params["spikein"]["function"] == "get_agendo_spikein"
    print("nfcore_3mrnaseq template test passed")


if __name__ == "__main__":
    main()
