#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
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


def make_fake_nextflow_bin(root: Path) -> Path:
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
        "  printf 'Run name: test-run\\n' > .nextflow.log\n"
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
    docker = bin_dir / "docker"
    docker.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    docker.chmod(0o755)
    return bin_dir


def test_launch_script() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-3mrnaseq-test-") as tmp:
        tmpdir = Path(tmp)
        fake_bin = make_fake_nextflow_bin(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text("sample,fastq_1,fastq_2,strandedness\nS1,R1.fastq.gz,R2.fastq.gz,forward\n", encoding="utf-8")
        results_dir = tmpdir / "results"
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["NFCORE_ARGS_LOG"] = str(tmpdir / "args.log")
        completed = subprocess.run(
            [
                "bash",
                str(TEMPLATE_DIR / "launch_nfcore_3mrnaseq.sh"),
                str(results_dir),
                str(samplesheet),
                "GRCh38",
                "UMI Second Strand SynthesisModule for QuantSeq FWD",
                "ERCC RNA Spike-in Mix",
                "16",
                "64GB",
            ],
            cwd=TEMPLATE_DIR,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        args_text = (tmpdir / "args.log").read_text(encoding="utf-8")
        assert "--outdir" in args_text
        assert str(results_dir) in args_text
        assert "--genome GRCh38_with_ERCC" in args_text
        assert "--with_umi" in args_text
        assert "--max_cpus 16" in args_text
        assert "--max_memory 64GB" in args_text
        assert (results_dir / "multiqc" / "multiqc_report.html").exists()
        assert (results_dir / "salmon" / "quant.sf").exists()


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


def main() -> None:
    test_launch_script()
    test_samplesheet_binding()
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    assert 'bash ./launch_nfcore_3mrnaseq.sh' in template_text
    assert '"${SAMPLESHEET}"' in template_text
    assert '"${GENOME}"' in template_text
    print("nfcore_3mrnaseq template test passed")


if __name__ == "__main__":
    main()
