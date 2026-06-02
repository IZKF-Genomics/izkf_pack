#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
FUNCTIONS_DIR = TEMPLATE_DIR.parent.parent / "functions"
UMI_KIT = "UMI Second Strand SynthesisModule for QuantSeq FWD"
SPIKEIN_KIT = "ERCC RNA Spike-in Mix"


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
        "  mkdir -p \"${outdir}/multiqc/star_salmon\" \"${outdir}/star_salmon\" \"${outdir}/pipeline_info\"\n"
        "  printf '<html>multiqc</html>\\n' > \"${outdir}/multiqc/star_salmon/multiqc_report.html\"\n"
        "  printf 'quant\\n' > \"${outdir}/star_salmon/quant.sf\"\n"
        "  printf '{\"params\":true}\\n' > \"${outdir}/pipeline_info/params_test.json\"\n"
        "  printf 'versions\\n' > \"${outdir}/pipeline_info/nf_core_rnaseq_software_mqc_versions.yml\"\n"
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
    linkar = bin_dir / "linkar"
    linkar.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    linkar.chmod(0o755)
    return bin_dir


def copy_runtime_template(tmpdir: Path) -> None:
    for name in ("run.py", "run.sh", "nextflow.config"):
        shutil.copy2(TEMPLATE_DIR / name, tmpdir / name)


def test_prepare_and_run_script() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-3mrnaseq-test-") as tmp:
        tmpdir = Path(tmp)
        copy_runtime_template(tmpdir)
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
        completed = subprocess.run(
            ["python3", "run.py", "--prepare"],
            cwd=tmpdir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        run_params_text = (tmpdir / "config" / "run_params.env").read_text(encoding="utf-8")
        assert "PIPELINE_VERSION" not in run_params_text
        assert "IGENOMES_BASE" not in run_params_text
        assert "EXTRA_SALMON_QUANT_ARGS" not in run_params_text
        assert "SAMPLESHEET" not in run_params_text
        assert "RESULTS_DIR" not in run_params_text
        assert "EFFECTIVE_GENOME=GRCh38_with_ERCC" in run_params_text
        assert "MAX_MEMORY=64.GB" in run_params_text
        assert (tmpdir / "samplesheet.csv").read_text(encoding="utf-8") == (
            "sample,fastq_1,fastq_2,strandedness\nS1,R1.fastq.gz,R2.fastq.gz,forward\n"
        )

        run_env = os.environ.copy()
        run_env["PATH"] = f"{fake_bin}:{run_env.get('PATH', '')}"
        run_env["NFCORE_ARGS_LOG"] = str(tmpdir / "args.log")
        for name in ("SAMPLESHEET", "GENOME", "UMI", "SPIKEIN", "MAX_CPUS", "MAX_MEMORY", "LINKAR_RESULTS_DIR"):
            run_env.pop(name, None)
        completed = subprocess.run(
            ["bash", "run.sh"],
            cwd=tmpdir,
            env=run_env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

        run_sh_text = (tmpdir / "run.sh").read_text(encoding="utf-8")
        assert 'source config/run_params.env' in run_sh_text
        assert 'pixi run nextflow run nf-core/rnaseq \\' in run_sh_text
        assert "-r 3.26.0 \\" in run_sh_text
        assert "-profile docker \\" in run_sh_text
        assert "--igenomes_base /data/shared/igenomes/ \\" in run_sh_text
        assert '--extra_salmon_quant_args="--noLengthCorrection" \\' in run_sh_text
        assert '--extra_star_align_args="--alignIntronMax 1000000 --alignIntronMin 20 --alignMatesGapMax 1000000 --alignSJoverhangMin 8 --outFilterMismatchNmax 999 --outFilterMultimapNmax 20 --outFilterType BySJout --outFilterMismatchNoverLmax 0.1 --clip3pAdapterSeq AAAAAAAA" \\' in run_sh_text
        assert 'UMI_ARGS+=(' in run_sh_text
        assert 'linkar collect "${script_dir}"' in run_sh_text
        args_text = (tmpdir / "args.log").read_text(encoding="utf-8")
        assert "nf-core/rnaseq" in args_text
        assert "-profile docker" in args_text
        assert "-c nextflow.config" in args_text
        assert "--input samplesheet.csv" in args_text
        assert "--outdir results" in args_text
        assert "--genome GRCh38_with_ERCC" in args_text
        assert "--with_umi" in args_text
        assert "--umitools_extract_method regex" in args_text
        assert "--max_cpus 16" in args_text
        assert "--max_memory 64.GB" in args_text
        assert (results_dir / "multiqc" / "star_salmon" / "multiqc_report.html").exists()
        assert (results_dir / "star_salmon" / "quant.sf").exists()
        assert (results_dir / "pipeline_info" / "params_test.json").exists()
        assert (results_dir / "pipeline_info" / "nf_core_rnaseq_software_mqc_versions.yml").exists()
        nextflow_config_text = (tmpdir / "nextflow.config").read_text(encoding="utf-8")
        assert "__EDIT_ME_MAX_CPUS__" not in nextflow_config_text
        assert "__EDIT_ME_MAX_MEMORY__" not in nextflow_config_text


def test_toggle_shorthand_normalization() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-3mrnaseq-toggle-test-") as tmp:
        tmpdir = Path(tmp)
        copy_runtime_template(tmpdir)
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
        env["GENOME"] = "Sscrofa11.1"
        env["UMI"] = "true"
        env["SPIKEIN"] = "yes"
        completed = subprocess.run(
            ["python3", "run.py", "--prepare"],
            cwd=tmpdir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

        run_env = os.environ.copy()
        run_env["PATH"] = f"{fake_bin}:{run_env.get('PATH', '')}"
        run_env["NFCORE_ARGS_LOG"] = str(tmpdir / "args.log")
        for name in ("SAMPLESHEET", "GENOME", "UMI", "SPIKEIN", "MAX_CPUS", "MAX_MEMORY", "LINKAR_RESULTS_DIR"):
            run_env.pop(name, None)
        completed = subprocess.run(
            ["bash", "run.sh"],
            cwd=tmpdir,
            env=run_env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

        args_text = (tmpdir / "args.log").read_text(encoding="utf-8")
        assert "--genome Sscrofa11.1_with_ERCC" in args_text
        assert "--with_umi" in args_text
        run_params_text = (tmpdir / "config" / "run_params.env").read_text(encoding="utf-8")
        assert f"UMI={shlex.quote(UMI_KIT)}" in run_params_text
        assert f"SPIKEIN={shlex.quote(SPIKEIN_KIT)}" in run_params_text


def test_none_string_normalization() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-3mrnaseq-none-test-") as tmp:
        tmpdir = Path(tmp)
        copy_runtime_template(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text(
            "sample,fastq_1,fastq_2,strandedness\nS1,R1.fastq.gz,R2.fastq.gz,forward\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["LINKAR_RESULTS_DIR"] = str(tmpdir / "results")
        env["SAMPLESHEET"] = str(samplesheet)
        env["GENOME"] = "GRCh38"
        env["UMI"] = "None"
        env["SPIKEIN"] = "None"
        completed = subprocess.run(
            ["python3", "run.py", "--prepare"],
            cwd=tmpdir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        run_params_text = (tmpdir / "config" / "run_params.env").read_text(encoding="utf-8")
        assert "UMI=''" in run_params_text
        assert "SPIKEIN=''" in run_params_text
        assert "EFFECTIVE_GENOME=GRCh38" in run_params_text


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
            (cache_dir / "12345.json").write_text(json.dumps({"organism": "chicken"}), encoding="utf-8")
            assert load_function("get_agendo_genome")(CachedContext()) == "GRCg7b"
            (cache_dir / "12345.json").write_text(
                json.dumps(
                    {
                        "organism": "other",
                        "fields": [
                            {
                                "name": "Specify &quot;other&quot; organism",
                                "value": "Gallus gallus domesticus",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            assert load_function("get_agendo_genome")(CachedContext()) == "GRCg7b"
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
                    "action": "Rerender with --genome or edit the generated parameters before execution.",
                    "fallback": "__EDIT_ME_GENOME__",
                }
            ]
        finally:
            if env_before is None:
                os.environ.pop("LINKAR_HOME", None)
            else:
                os.environ["LINKAR_HOME"] = env_before


def main() -> None:
    test_prepare_and_run_script()
    test_toggle_shorthand_normalization()
    test_none_string_normalization()
    test_samplesheet_binding()
    test_agendo_bindings_use_cached_metadata()
    test_agendo_genome_unknown_organism_returns_placeholder()
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    nextflow_config_text = (TEMPLATE_DIR / "nextflow.config").read_text(encoding="utf-8")
    assert "entry: run.sh" in template_text
    assert "python3 ./run.py --prepare" in template_text
    assert "- pixi" in template_text
    assert "- python3" in template_text
    assert 'source config/run_params.env' in run_sh_text
    assert 'pixi run nextflow run nf-core/rnaseq' in run_sh_text
    assert '-r 3.26.0' in run_sh_text
    assert '-profile docker' in run_sh_text
    assert '"${RESOURCE_ARGS[@]}"' in run_sh_text
    assert '"${UMI_ARGS[@]}"' in run_sh_text
    assert 'linkar collect "${script_dir}"' in run_sh_text
    assert 'linkar clean "${script_dir}" --yes' in run_sh_text
    assert 'config" / "run_params.env"' in run_py_text
    assert 'copy_samplesheet' in run_py_text
    assert 'DEFAULT_PIPELINE_VERSION' not in run_py_text
    assert 'command_pretty' not in run_py_text
    assert 'runtime_command.json' not in run_py_text
    assert 'UMI Second Strand SynthesisModule for QuantSeq FWD' in run_py_text
    assert 'ERCC RNA Spike-in Mix' in run_py_text
    assert 'normalize_toggle_param' in run_py_text
    assert "path: pipeline_info/params_*.json" in template_text
    assert "rendered_samplesheet:" in template_text
    assert "path: ../samplesheet.csv" in template_text
    assert "Output paths and globs are resolved relative to LINKAR_RESULTS_DIR" in template_text
    assert "__EDIT_ME_MAX_CPUS__" not in nextflow_config_text
    assert "__EDIT_ME_MAX_MEMORY__" not in nextflow_config_text
    assert "star_index" not in nextflow_config_text
    assert "bowtie2_index" not in nextflow_config_text
    assert "bwa_index" not in nextflow_config_text
    assert "salmon_index" not in nextflow_config_text
    assert "star         = '/data/ref_genomes/GRCm39/indices/star'" in nextflow_config_text
    assert "salmon       = '/data/ref_genomes/GRCm39/indices/salmon'" in nextflow_config_text
    assert "bed12" not in nextflow_config_text
    assert "transcript_fasta" not in nextflow_config_text
    pack_text = (TEMPLATE_DIR.parent.parent / "linkar_pack.yaml").read_text(encoding="utf-8")
    pack_data = yaml.safe_load(pack_text)
    nfcore_params = pack_data["templates"]["nfcore_3mrnaseq"]["params"]
    assert nfcore_params["umi"]["function"] == "get_agendo_umi"
    assert nfcore_params["spikein"]["function"] == "get_agendo_spikein"
    print("nfcore_3mrnaseq template test passed")


if __name__ == "__main__":
    main()
