#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent
FUNCTIONS_DIR = TEMPLATE_DIR.parent.parent / "functions"


def load_binding():
    path = FUNCTIONS_DIR / "generate_nfcore_smrnaseq_samplesheet.py"
    spec = importlib.util.spec_from_file_location("test_generate_nfcore_smrnaseq_samplesheet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load binding: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve


def copy_runtime_template(destination: Path) -> None:
    for name in ("run.py", "run.sh", "nextflow.config"):
        shutil.copy2(TEMPLATE_DIR / name, destination / name)


def make_fake_bin(root: Path) -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    nextflow = bin_dir / "nextflow"
    nextflow.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" > \"${NFCORE_ARGS_LOG:?}\"\n"
        "mkdir -p results/multiqc results/mirna_quant/mirtop results/pipeline_info\n"
        "printf '<html>multiqc</html>\\n' > results/multiqc/multiqc_report.html\n"
        "printf 'miRNA\\tS1\\n' > results/mirna_quant/mirtop/mirna.tsv\n"
        "printf '{}\\n' > results/pipeline_info/params.json\n"
        "printf 'versions\\n' > results/pipeline_info/software_versions.yml\n",
        encoding="utf-8",
    )
    nextflow.chmod(0o755)
    pixi = bin_dir / "pixi"
    pixi.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == install ]]; then exit 0; fi\n"
        "if [[ \"${1:-}\" == run && \"${2:-}\" == nextflow ]]; then shift 2; exec \"$(dirname \"$0\")/nextflow\" \"$@\"; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    pixi.chmod(0o755)
    for name in ("docker", "linkar"):
        executable = bin_dir / name
        executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    return bin_dir


def test_prepare_and_run() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-smrnaseq-") as tmp:
        work = Path(tmp)
        copy_runtime_template(work)
        samplesheet = work / "source.csv"
        samplesheet.write_text("sample,fastq_1,fastq_2\nPig_1,/reads/Pig_1_R1.fastq.gz,\n", encoding="utf-8")
        mirna_gtf = work / "ssc.gff3"
        mature = work / "ssc_mature.fa"
        hairpin = work / "ssc_hairpin.fa"
        mirna_gtf.write_text("##gff-version 3\n", encoding="utf-8")
        mature.write_text(">ssc-miR-1\nACGT\n", encoding="utf-8")
        hairpin.write_text(">ssc-mir-1\nACGTACGT\n", encoding="utf-8")
        fake_bin = make_fake_bin(work)
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fake_bin}:{env.get('PATH', '')}",
                "NFCORE_ARGS_LOG": str(work / "args.log"),
                "LINKAR_RESULTS_DIR": str(work / "results"),
                "LINKAR_PROJECT_DIR": str(work / "project"),
                "SAMPLESHEET": str(samplesheet),
                "GENOME": "Sscrofa11.1",
                "MIRTRACE_SPECIES": "ssc",
                "MIRNA_GTF": str(mirna_gtf),
                "MATURE": str(mature),
                "HAIRPIN": str(hairpin),
                "THREE_PRIME_ADAPTER": "ADAPTER",
                "WITH_UMI": "true",
                "UMITOOLS_EXTRACT_METHOD": "regex",
                "UMITOOLS_BC_PATTERN": "^(?P<umi_1>.{8}).*",
                "SKIP_UMI_EXTRACT_BEFORE_DEDUP": "false",
                "SAVE_REFERENCE": "true",
                "SAVE_INTERMEDIATES": "true",
                "MAX_CPUS": "16",
                "MAX_MEMORY": "64GB",
            }
        )
        prepared = subprocess.run(
            ["python3", "run.py", "--prepare"], cwd=work, env=env, text=True, capture_output=True, check=False
        )
        assert prepared.returncode == 0, prepared.stderr
        runtime = (work / "config" / "run_params.env").read_text(encoding="utf-8")
        assert "GENOME=Sscrofa11.1" in runtime
        assert "MIRTRACE_SPECIES=ssc" in runtime
        assert f"MIRNA_GTF={mirna_gtf}" in runtime
        assert f"MATURE={mature}" in runtime
        assert f"HAIRPIN={hairpin}" in runtime
        assert "MAX_MEMORY=64.GB" in runtime
        assert "WITH_UMI=true" in runtime
        assert (work / "samplesheet.csv").read_text(encoding="utf-8") == samplesheet.read_text(encoding="utf-8")
        resources = (work / "config" / "resources.config").read_text(encoding="utf-8")
        assert "resourceLimits" in resources
        assert "cpus: 16" in resources
        assert "memory: 64.GB" in resources

        run_env = env.copy()
        for name in (
            "SAMPLESHEET", "GENOME", "MIRTRACE_SPECIES", "MIRNA_GTF", "MATURE", "HAIRPIN",
            "THREE_PRIME_ADAPTER", "WITH_UMI",
            "UMITOOLS_EXTRACT_METHOD", "UMITOOLS_BC_PATTERN", "SKIP_UMI_EXTRACT_BEFORE_DEDUP",
            "SAVE_REFERENCE", "SAVE_INTERMEDIATES", "MAX_CPUS", "MAX_MEMORY", "LINKAR_RESULTS_DIR",
        ):
            run_env.pop(name, None)
        completed = subprocess.run(
            ["bash", "run.sh"], cwd=work, env=run_env, text=True, capture_output=True, check=False
        )
        assert completed.returncode == 0, completed.stderr
        args = (work / "args.log").read_text(encoding="utf-8")
        for expected in (
            "nf-core/smrnaseq", "-r 2.4.1", "-profile docker", "-resume",
            "-c config/resources.config",
            "--input samplesheet.csv", "--genome Sscrofa11.1", "--mirtrace_species ssc",
            f"--mirna_gtf {mirna_gtf}", f"--mature {mature}", f"--hairpin {hairpin}",
            "--three_prime_adapter ADAPTER", "--with_umi", "--umitools_extract_method regex",
            "--skip_umi_extract_before_dedup false", "--save_reference", "--save_intermediates",
        ):
            assert expected in args, (expected, args)
        assert "--max_cpus" not in args
        assert "--max_memory" not in args
        assert (work / "results" / "multiqc" / "multiqc_report.html").exists()
        assert (work / "results" / "mirna_quant" / "mirtop" / "mirna.tsv").exists()


class FakeProject:
    def __init__(self, fastqs: list[str]) -> None:
        self.data = {"templates": [{"id": "demultiplex", "outputs": {"demux_fastq_files": fastqs}}]}


class FakeContext:
    def __init__(self, fastqs: list[str]) -> None:
        self.project = FakeProject(fastqs)


def test_samplesheet_binding() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-smrnaseq-binding-") as tmp:
        root = Path(tmp)
        r1 = root / "Pig_A_S1_R1_001.fastq.gz"
        r2 = root / "Pig_A_S1_R2_001.fastq.gz"
        single = root / "Pig_B_S2_R1_001.fastq.gz"
        unassigned = root / "Undetermined_S0_R1_001.fastq.gz"
        for path in (r1, r2, single, unassigned):
            path.write_text("FASTQ\n", encoding="utf-8")
        old_home = os.environ.get("LINKAR_HOME")
        os.environ["LINKAR_HOME"] = str(root / "linkar-home")
        try:
            output = Path(load_binding()(FakeContext([str(r1), str(r2), str(single), str(unassigned)])))
        finally:
            if old_home is None:
                os.environ.pop("LINKAR_HOME", None)
            else:
                os.environ["LINKAR_HOME"] = old_home
        rows = list(csv.reader(output.open(encoding="utf-8")))
        assert rows[0] == ["sample", "fastq_1", "fastq_2"]
        assert [row[0] for row in rows[1:]] == ["Pig_A", "Pig_B"]
        assert rows[1][2] == str(r2.resolve())
        assert rows[2][2] == ""


def main() -> None:
    test_prepare_and_run()
    test_samplesheet_binding()
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    pack_text = (TEMPLATE_DIR.parent.parent / "linkar_pack.yaml").read_text(encoding="utf-8")
    assert "id: nfcore_smrnaseq" in template_text
    assert "version: 0.2.0" in template_text
    assert "mode: render" in template_text
    assert "entry: run.sh" in template_text
    assert "nfcore_smrnaseq:" in pack_text
    assert "function: generate_nfcore_smrnaseq_samplesheet" in pack_text
    print("nfcore_smrnaseq template test passed")


if __name__ == "__main__":
    main()
