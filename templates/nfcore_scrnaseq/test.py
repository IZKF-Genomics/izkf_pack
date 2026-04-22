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
        "  aligner=''\n"
        "  for ((i=1; i<=$#; i++)); do\n"
        "    if [[ \"${!i}\" == \"--outdir\" ]]; then\n"
        "      j=$((i+1))\n"
        "      outdir=\"${!j}\"\n"
        "    fi\n"
        "    if [[ \"${!i}\" == \"--aligner\" ]]; then\n"
        "      j=$((i+1))\n"
        "      aligner=\"${!j}\"\n"
        "    fi\n"
        "  done\n"
        "  mkdir -p \"${outdir}/multiqc\" \"${outdir}/pipeline_info\" \"${outdir}/${aligner}/mtx_conversions\"\n"
        "  printf '<html>multiqc</html>\\n' > \"${outdir}/multiqc/multiqc_report.html\"\n"
        "  printf 'trace\\n' > \"${outdir}/pipeline_info/execution_trace.txt\"\n"
        "  printf 'matrix\\n' > \"${outdir}/${aligner}/mtx_conversions/combined_filtered_matrix.h5ad\"\n"
        "  printf 'matrix\\n' > \"${outdir}/${aligner}/mtx_conversions/sample_a_raw_matrix.h5ad\"\n"
        "  printf 'Run name: scrnaseq-test-run\\n' > .nextflow.log\n"
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


def make_reference_tree(root: Path) -> None:
    refs = {
        "GRCh38": (
            "GRCh38.primary_assembly.genome.fa",
            "gencode.v49.primary_assembly.annotation.gtf",
        ),
        "GRCz11": (
            "Danio_rerio.GRCz11.dna.toplevel.fa",
            "Danio_rerio.GRCz11.115.gtf",
        ),
    }
    for genome, (fasta_name, gtf_name) in refs.items():
        src_dir = root / "data" / "ref_genomes" / genome / "src"
        star_dir = root / "data" / "ref_genomes" / genome / "indices" / "star"
        src_dir.mkdir(parents=True, exist_ok=True)
        star_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / fasta_name).write_text(">chr1\nACGT\n", encoding="utf-8")
        (src_dir / gtf_name).write_text("chr1\tsrc\tgene\t1\t4\t.\t+\t.\tgene_id \"g1\";\n", encoding="utf-8")
        (star_dir / "Genome").write_text("star\n", encoding="utf-8")

    cellranger_dir = root / "data" / "shared" / "10xGenomics" / "refs" / "refdata-gex-GRCh38-2024-A"
    cellranger_dir.mkdir(parents=True, exist_ok=True)
    (cellranger_dir / "reference.json").write_text("{}\n", encoding="utf-8")


def prepare_template_copy(root: Path) -> Path:
    dest = root / "template"
    shutil = __import__("shutil")
    shutil.copytree(TEMPLATE_DIR, dest)
    run_py = dest / "run.py"
    text = run_py.read_text(encoding="utf-8")
    text = text.replace('"/data/ref_genomes/', f'"{root}/data/ref_genomes/')
    text = text.replace('"/data/shared/10xGenomics/refs/', f'"{root}/data/shared/10xGenomics/refs/')
    run_py.write_text(text, encoding="utf-8")
    return dest


def test_rendered_run_script_star() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-scrnaseq-star-test-") as tmp:
        tmpdir = Path(tmp)
        make_reference_tree(tmpdir)
        template_dir = prepare_template_copy(tmpdir)
        fake_bin = make_fake_runtime_bin(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text(
            "sample,fastq_1,fastq_2\nS1,R1.fastq.gz,R2.fastq.gz\n",
            encoding="utf-8",
        )
        results_dir = template_dir / "results"
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["NFCORE_ARGS_LOG"] = str(tmpdir / "args.log")
        env["LINKAR_RESULTS_DIR"] = str(results_dir)
        env["LINKAR_PROJECT_DIR"] = str(tmpdir / "scrna_project")
        env["SAMPLESHEET"] = str(samplesheet)
        env["GENOME"] = "GRCz11"
        env["ALIGNER"] = "star"
        env["PROTOCOL"] = "10XV3"
        env["EXPECTED_CELLS"] = "5000"
        env["MAX_CPUS"] = "16"
        env["MAX_MEMORY"] = "64GB"
        completed = subprocess.run(
            ["bash", str(template_dir / "run.sh"), "-resume"],
            cwd=template_dir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        args_text = (tmpdir / "args.log").read_text(encoding="utf-8")
        assert "nf-core/scrnaseq" in args_text
        assert "-profile docker" in args_text
        assert "-c nextflow.config" in args_text
        assert "--input samplesheet.csv" in args_text
        assert "--outdir results" in args_text
        assert "--aligner star" in args_text
        assert "--protocol 10XV3" in args_text
        assert "--genome GRCz11" in args_text
        assert "--igenomes_ignore true" in args_text
        assert "--fasta " not in args_text
        assert "--gtf " not in args_text
        assert "--star_index " not in args_text
        assert "--skip_cellbender true" in args_text
        assert "-resume" in args_text
        params_text = (template_dir / "params.yaml").read_text(encoding="utf-8")
        assert 'aligner: "star"' in params_text
        assert 'protocol: "10XV3"' in params_text
        assert 'star_index: "' in params_text
        assert "cellranger_index" not in params_text
        staged_rows = list(csv.DictReader((template_dir / "samplesheet.csv").open(encoding="utf-8")))
        assert staged_rows[0]["expected_cells"] == "5000"
        assert (results_dir / "multiqc" / "multiqc_report.html").exists()
        assert (results_dir / "pipeline_info" / "execution_trace.txt").exists()
        assert (template_dir / "selected_matrix.h5ad").exists()
        assert os.readlink(template_dir / "selected_matrix.h5ad") == "results/star/mtx_conversions/combined_filtered_matrix.h5ad"
        nextflow_config_text = (template_dir / "nextflow.config").read_text(encoding="utf-8")
        assert "cpus: 16" in nextflow_config_text
        assert "memory: '64.GB'" in nextflow_config_text
        runtime_payload = json.loads((results_dir / "runtime_command.json").read_text(encoding="utf-8"))
        assert runtime_payload["template"] == "nfcore_scrnaseq"
        assert runtime_payload["pipeline"] == "nf-core/scrnaseq"
        assert runtime_payload["pipeline_version"] == "4.1.0"
        assert runtime_payload["params"]["genome"] == "GRCz11"
        assert runtime_payload["params"]["aligner"] == "star"
        assert runtime_payload["params"]["protocol"] == "10XV3"
        assert runtime_payload["params"]["expected_cells"] == "5000"
        assert runtime_payload["params"]["skip_cellbender"] is True
        assert runtime_payload["artifacts"]["params_file"] == str(template_dir / "params.yaml")
        versions_payload = json.loads((results_dir / "software_versions.json").read_text(encoding="utf-8"))
        versions = {entry["name"]: entry for entry in versions_payload["software"]}
        assert versions["nextflow"]["version"] == "nextflow version 24.10.0"
        assert versions["aligner"]["version"] == "star"
        assert versions["protocol"]["version"] == "10XV3"
        selection_payload = json.loads((results_dir / "matrix_selection.json").read_text(encoding="utf-8"))
        assert selection_payload["selected"].endswith("combined_filtered_matrix.h5ad")


def test_cellranger_auto_protocol() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-scrnaseq-cellranger-test-") as tmp:
        tmpdir = Path(tmp)
        make_reference_tree(tmpdir)
        template_dir = prepare_template_copy(tmpdir)
        fake_bin = make_fake_runtime_bin(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text(
            "sample,fastq_1,fastq_2\nS1,R1.fastq.gz,R2.fastq.gz\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["NFCORE_ARGS_LOG"] = str(tmpdir / "args.log")
        env["LINKAR_RESULTS_DIR"] = str(template_dir / "results")
        env["LINKAR_PROJECT_DIR"] = str(tmpdir / "scrna_project")
        env["SAMPLESHEET"] = str(samplesheet)
        env["GENOME"] = "GRCh38"
        env["ALIGNER"] = "cellranger"
        env["CELLRANGER_INDEX"] = str(tmpdir / "scrna_project")
        rendered_run_script = template_dir / "run.generated.sh"
        completed = subprocess.run(
            ["python3", str(template_dir / "run.py"), "--render-only", "--run-script", str(rendered_run_script)],
            cwd=template_dir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        params_text = (template_dir / "params.yaml").read_text(encoding="utf-8")
        assert 'aligner: "cellranger"' in params_text
        assert 'protocol: "auto"' in params_text
        assert 'cellranger_index: "' in params_text
        run_text = rendered_run_script.read_text(encoding="utf-8")
        assert "--genome GRCh38" in run_text
        assert "--cellranger_index" not in run_text


def test_render_only_with_placeholder_genome_writes_guarded_run_script() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-scrnaseq-placeholder-test-") as tmp:
        tmpdir = Path(tmp)
        make_reference_tree(tmpdir)
        template_dir = prepare_template_copy(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text(
            "sample,fastq_1,fastq_2\nS1,R1.fastq.gz,R2.fastq.gz\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["LINKAR_RESULTS_DIR"] = str(template_dir / "results")
        env["SAMPLESHEET"] = str(samplesheet)
        env["GENOME"] = "__EDIT_ME_GENOME__"
        env["ALIGNER"] = "cellranger"
        env["CELLRANGER_INDEX"] = str(tmpdir / "data" / "shared" / "10xGenomics" / "refs" / "refdata-gex-GRCh38-2024-A")
        rendered_run_script = template_dir / "run.generated.sh"
        completed = subprocess.run(
            ["python3", str(template_dir / "run.py"), "--render-only", "--run-script", str(rendered_run_script)],
            cwd=template_dir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        params_text = (template_dir / "params.yaml").read_text(encoding="utf-8")
        assert 'genome: "__EDIT_ME_GENOME__"' in params_text
        assert 'fasta: "__EDIT_ME_FASTA__"' in params_text
        assert 'gtf: "__EDIT_ME_GTF__"' in params_text
        assert 'cellranger_index: "' in params_text
        run_text = rendered_run_script.read_text(encoding="utf-8")
        assert 'grep -q "__EDIT_ME_" "${script_dir}/params.yaml"' in run_text
        rerun = subprocess.run(
            ["bash", str(rendered_run_script)],
            cwd=template_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        assert rerun.returncode != 0
        assert "unresolved placeholders detected in params.yaml" in rerun.stderr


def test_star_requires_non_auto_protocol() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-scrnaseq-protocol-test-") as tmp:
        tmpdir = Path(tmp)
        make_reference_tree(tmpdir)
        template_dir = prepare_template_copy(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text("sample,fastq_1,fastq_2\nS1,R1.fastq.gz,R2.fastq.gz\n", encoding="utf-8")
        env = os.environ.copy()
        env["LINKAR_RESULTS_DIR"] = str(template_dir / "results")
        env["SAMPLESHEET"] = str(samplesheet)
        env["GENOME"] = "GRCz11"
        env["ALIGNER"] = "star"
        env["PROTOCOL"] = "auto"
        completed = subprocess.run(
            ["python3", str(template_dir / "run.py"), "--render-only", "--run-script", str(template_dir / "run.generated.sh")],
            cwd=template_dir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode != 0
        combined = f"{completed.stdout}\n{completed.stderr}"
        assert "protocol=auto is only supported when aligner=cellranger" in combined


def test_star_requires_explicit_protocol_message() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-scrnaseq-missing-protocol-test-") as tmp:
        tmpdir = Path(tmp)
        make_reference_tree(tmpdir)
        template_dir = prepare_template_copy(tmpdir)
        samplesheet = tmpdir / "samplesheet.csv"
        samplesheet.write_text("sample,fastq_1,fastq_2\nS1,R1.fastq.gz,R2.fastq.gz\n", encoding="utf-8")
        env = os.environ.copy()
        env["LINKAR_RESULTS_DIR"] = str(template_dir / "results")
        env["SAMPLESHEET"] = str(samplesheet)
        env["GENOME"] = "GRCz11"
        env["ALIGNER"] = "star"
        completed = subprocess.run(
            ["python3", str(template_dir / "run.py"), "--render-only", "--run-script", str(template_dir / "run.generated.sh")],
            cwd=template_dir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode != 0
        combined = f"{completed.stdout}\n{completed.stderr}"
        assert "protocol is required for aligner=star" in combined
        assert "--protocol 10XV3" in combined


class FakeProject:
    def __init__(self, fastq_files: list[str], *, expected_cells: str = "") -> None:
        self.data = {
            "templates": [
                {
                    "id": "demultiplex",
                    "outputs": {"demux_fastq_files": fastq_files},
                }
            ]
        }
        self.expected_cells = expected_cells


class FakeTemplate:
    root = TEMPLATE_DIR


class FakeContext:
    def __init__(self, fastq_files: list[str], *, expected_cells: str = "") -> None:
        self.project = FakeProject(fastq_files, expected_cells=expected_cells)
        self.template = FakeTemplate()
        self.resolved_params = {"expected_cells": expected_cells} if expected_cells else {}

    def latest_output(self, key: str, template_id: str | None = None):
        for entry in reversed(self.project.data["templates"]):
            if template_id is not None and entry["id"] != template_id:
                continue
            outputs = entry.get("outputs") or {}
            if key in outputs:
                return outputs[key]
        return None


def test_samplesheet_binding() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-scrnaseq-samplesheet-test-") as tmp:
        tmpdir = Path(tmp)
        fastq_dir = tmpdir / "demux-results" / "output"
        fastq_dir.mkdir(parents=True)
        sample_r1 = fastq_dir / "SC_A_S1_L001_R1_001.fastq.gz"
        sample_r2 = fastq_dir / "SC_A_S1_L001_R2_001.fastq.gz"
        sample_r1.write_text("r1\n", encoding="utf-8")
        sample_r2.write_text("r2\n", encoding="utf-8")
        resolve = load_function("generate_nfcore_scrnaseq_samplesheet")
        output = Path(resolve(FakeContext([str(sample_r1), str(sample_r2)], expected_cells="1234")))
        assert output.exists()
        rows = list(csv.reader(output.open(encoding="utf-8")))
        assert rows[0] == ["sample", "fastq_1", "fastq_2", "expected_cells"]
        assert rows[1][0] == "SC_A"
        assert rows[1][3] == "1234"


def test_agendo_genome_without_request_id_returns_placeholder() -> None:
    class MissingAgendoContext:
        def __init__(self) -> None:
            self.resolved_params = {}
            self.warnings = []

        def warn(self, message: str, *, action: str | None = None, fallback=None) -> None:
            self.warnings.append(
                {"message": message, "action": action, "fallback": fallback}
            )

    ctx = MissingAgendoContext()
    assert load_function("get_agendo_genome")(ctx) == "__EDIT_ME_GENOME__"
    assert ctx.warnings == [
        {
            "message": "No agendo_id provided; could not derive genome from Agendo metadata.",
            "action": "Pass --agendo-id or rerender with --genome before execution.",
            "fallback": "__EDIT_ME_GENOME__",
        }
    ]


def main() -> None:
    test_rendered_run_script_star()
    test_cellranger_auto_protocol()
    test_render_only_with_placeholder_genome_writes_guarded_run_script()
    test_star_requires_non_auto_protocol()
    test_samplesheet_binding()
    test_agendo_genome_without_request_id_returns_placeholder()
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    assert "python3 ./run.py --run-script ./run.sh" in template_text
    assert "python3 ./run.py --render-only --run-script ./run.sh" in template_text
    assert "- pixi" in template_text
    assert "- python3" in template_text
    assert "selected_matrix_h5ad" in template_text
    assert 'resolved_run.sh' in run_sh_text
    assert 'exec python3 "${script_dir}/run.py" --run-script "${script_dir}/resolved_run.sh"' in run_sh_text
    assert 'runtime_command.json' in run_py_text
    assert 'params.yaml' in run_py_text
    assert 'SUPPORTED_ALIGNERS' in run_py_text
    assert 'protocol=auto is only supported when aligner=cellranger' in run_py_text
    assert 'command.append("-resume")' in run_py_text
    assert 'selected_matrix.h5ad' in readme_text
    pack_text = (TEMPLATE_DIR.parent.parent / "linkar_pack.yaml").read_text(encoding="utf-8")
    pack_data = yaml.safe_load(pack_text)
    nfcore_params = pack_data["templates"]["nfcore_scrnaseq"]["params"]
    assert nfcore_params["samplesheet"]["function"] == "generate_nfcore_scrnaseq_samplesheet"
    assert nfcore_params["genome"]["function"] == "get_agendo_genome"
    print("nfcore_scrnaseq template test passed")


if __name__ == "__main__":
    main()
