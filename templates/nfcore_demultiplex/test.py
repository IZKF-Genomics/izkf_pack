#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
PACK_ROOT = TEMPLATE_DIR.parent.parent
FUNCTIONS_DIR = PACK_ROOT / "functions"


def load_function(name: str):
    path = FUNCTIONS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load function module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve


def load_function_module(name: str):
    path = FUNCTIONS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load function module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        "  flowcell='FLOWCELL'\n"
        "  for ((i=1; i<=$#; i++)); do\n"
        "    if [[ \"${!i}\" == \"--outdir\" ]]; then\n"
        "      j=$((i+1)); outdir=\"${!j}\"\n"
        "    fi\n"
        "    if [[ \"${!i}\" == \"--flowcell_id\" ]]; then\n"
        "      j=$((i+1)); flowcell=\"${!j}\"\n"
        "    fi\n"
        "  done\n"
        "  mkdir -p \"${outdir}/${flowcell}\" \"${outdir}/multiqc\" \"${outdir}/pipeline_info\" \"${outdir}/fastqc\"\n"
        "  printf '@S1/1\\nAC\\n+\\nII\\n' | gzip -c > \"${outdir}/${flowcell}/S1_S1_L001_R1_001.fastq.gz\"\n"
        "  printf '@S1/2\\nTG\\n+\\nII\\n' | gzip -c > \"${outdir}/${flowcell}/S1_S1_L001_R2_001.fastq.gz\"\n"
        "  printf '@S2/1\\nAC\\n+\\nII\\n' | gzip -c > \"${outdir}/${flowcell}/S2_S2_L001_R1_001.fastq.gz\"\n"
        "  printf '@S2/2\\nTG\\n+\\nII\\n' | gzip -c > \"${outdir}/${flowcell}/S2_S2_L001_R2_001.fastq.gz\"\n"
        "  printf '<html>global multiqc</html>\\n' > \"${outdir}/multiqc/multiqc_report.html\"\n"
        "  printf '<html>S1 fastqc</html>\\n' > \"${outdir}/fastqc/S1_fastqc.html\"\n"
        "  printf '<html>S2 fastqc</html>\\n' > \"${outdir}/fastqc/S2_fastqc.html\"\n"
        "  printf '{\"params\":true}\\n' > \"${outdir}/pipeline_info/params_test.json\"\n"
        "  printf 'versions\\n' > \"${outdir}/pipeline_info/nf_core_demultiplex_software_versions.yml\"\n"
        "  printf 'Run name: demultiplex-test-run\\n' > .nextflow.log\n"
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
        "if [[ \"${1:-}\" == \"--version\" ]]; then\n"
        "  echo 'pixi 0.42.1'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == \"install\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == \"run\" && \"${2:-}\" == \"nextflow\" ]]; then\n"
        "  shift 2\n"
        f"exec {str(nextflow)} \"$@\"\n"
        "fi\n"
        "if [[ \"${1:-}\" == \"run\" && \"${2:-}\" == \"multiqc\" ]]; then\n"
        "  shift 2\n"
        "  outdir=''\n"
        "  filename='multiqc_report.html'\n"
        "  for ((i=1; i<=$#; i++)); do\n"
        "    if [[ \"${!i}\" == \"--outdir\" ]]; then\n"
        "      j=$((i+1)); outdir=\"${!j}\"\n"
        "    fi\n"
        "    if [[ \"${!i}\" == \"--filename\" ]]; then\n"
        "      j=$((i+1)); filename=\"${!j}\"\n"
        "    fi\n"
        "  done\n"
        "  mkdir -p \"${outdir}\"\n"
        "  printf '<html>project multiqc</html>\\n' > \"${outdir}/${filename}\"\n"
        "  exit 0\n"
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
    for name in (
        "run.py",
        "run.sh",
        "build_project_views.py",
        "check_empty_fastqs.py",
        "check_manifest.py",
        "recover_demultiplex_fastqs.py",
        "nextflow.config",
        "software_versions_spec.yaml",
    ):
        shutil.copy2(TEMPLATE_DIR / name, tmpdir / name)


def write_illumina_run(root: Path) -> tuple[Path, Path]:
    raw = root / "260407_NB501289_0992_AHLHGVBGYX"
    (raw / "Data" / "Intensities" / "BaseCalls").mkdir(parents=True)
    (raw / "RunInfo.xml").write_text("<RunInfo />\n", encoding="utf-8")
    samplesheet = root / "SampleSheet.csv"
    samplesheet.write_text(
        "[Header]\n"
        "IEMFileVersion,4\n"
        "[Reads]\n"
        "151\n"
        "151\n"
        "[Settings]\n"
        "AdapterRead1,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA\n"
        "AdapterRead2,AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT\n"
        "AdapterBehavior,trim\n"
        "[Data]\n"
        "Sample_ID,Sample_Name,Sample_Project,index\n"
        "S1,S1,Project_A,ACGTACGT\n"
        "S2,S2,Project_B,TGCATGCA\n",
        encoding="utf-8",
    )
    return raw, samplesheet


def write_aviti_run(root: Path) -> Path:
    raw = root / "AVITI_RUN_001"
    raw.mkdir()
    (raw / "RunManifest.csv").write_text(
        "[Run]\n"
        "RunName,AVITI_RUN_001\n"
        "[Samples]\n"
        "SampleName,Project,Index1,Index2\n"
        "S1,Project_A,ACGTACGT,TGCATGCA\n"
        "S2,Project_B,TGCATGCA,ACGTACGT\n"
        "# Fill in real samples before sequencing.\n"
        "ExampleSample_1,DefaultProject,AAAAAAAAAA,GGGGGGGGGG\n"
        "ExampleSample_1,DefaultProject,TTTTTTTTTT,CCCCCCCCCC\n",
        encoding="utf-8",
    )
    return raw


def run_template(tmpdir: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        ["bash", "run.sh"],
        cwd=tmpdir,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def test_illumina_run_script() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-demux-illumina-") as tmp:
        tmpdir = Path(tmp)
        copy_runtime_template(tmpdir)
        fake_bin = make_fake_runtime_bin(tmpdir)
        raw_run_dir, samplesheet = write_illumina_run(tmpdir)
        env = {
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            "RAW_RUN_DIR": str(raw_run_dir),
            "FLOWCELL_SAMPLESHEET": str(samplesheet),
            "MAX_CPUS": "16",
            "MAX_MEMORY": "64GB",
            "NFCORE_ARGS_LOG": str(tmpdir / "args.log"),
            "LINKAR_PACK_ROOT": str(PACK_ROOT),
        }
        completed = subprocess.run(
            ["python3", "run.py", "--prepare"],
            cwd=tmpdir,
            env={**os.environ, **env},
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        run_params = (tmpdir / "config" / "run_params.env").read_text(encoding="utf-8")
        assert "PLATFORM=illumina" in run_params
        assert "DEMULTIPLEXER=bclconvert" in run_params
        assert "FLOWCELL_ID=HLHGVBGYX" in run_params
        assert "MERGE_LANES=true" in run_params
        assert "V1_SCHEMA=true" in run_params
        assert "REMOVE_SAMPLESHEET_ADAPTER=false" in run_params
        assert "MAX_MEMORY=64.GB" in run_params
        assert "DEMUX_CPUS=''" in run_params
        assert "FALCO_CPUS=''" in run_params
        staged_samplesheet = (tmpdir / "flowcell_samplesheet.csv").read_text(encoding="utf-8")
        assert "AdapterRead1,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA" in staged_samplesheet
        assert "AdapterRead2,AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT" in staged_samplesheet
        assert "AdapterBehavior,trim" in staged_samplesheet

        run_env = os.environ.copy()
        run_env["PATH"] = f"{fake_bin}:{run_env.get('PATH', '')}"
        run_env["NFCORE_ARGS_LOG"] = str(tmpdir / "args.log")
        for name in ("RAW_RUN_DIR", "FLOWCELL_SAMPLESHEET", "MAX_CPUS", "MAX_MEMORY"):
            run_env.pop(name, None)
        completed = run_template(tmpdir, run_env)
        assert completed.returncode == 0, completed.stderr

        run_sh_text = (tmpdir / "run.sh").read_text(encoding="utf-8")
        assert 'export NXF_VER="${NXF_VER:-25.10.2}"' in run_sh_text
        assert 'pixi run nextflow run nf-core/demultiplex \\' in run_sh_text
        assert "--flowcell_path \"${RAW_RUN_DIR}\" \\" in run_sh_text
        assert "--demultiplexer \"${DEMULTIPLEXER}\" \\" in run_sh_text
        assert "--trim_fastq false \\" in run_sh_text
        args_text = (tmpdir / "args.log").read_text(encoding="utf-8")
        assert "nf-core/demultiplex" in args_text
        assert "-r 1.7.1" in args_text
        assert "--flowcell_id HLHGVBGYX" in args_text
        assert "--demultiplexer bclconvert" in args_text
        assert "--remove_samplesheet_adapter false" in args_text
        assert "--max_cpus" not in args_text
        assert "--max_memory" not in args_text
        nextflow_config_text = (tmpdir / "nextflow.config").read_text(encoding="utf-8")
        assert "resourceLimits" in nextflow_config_text
        assert "def demuxCpus" in nextflow_config_text
        assert "def falcoCpus" in nextflow_config_text
        assert "def mergeLanes" in nextflow_config_text
        assert "--no-lane-splitting true" in nextflow_config_text
        assert "withName: FALCO" in nextflow_config_text
        assert "maxForks = falcoMaxForks" in nextflow_config_text
        assert "--skip-empty-fq-files" not in nextflow_config_text
        assert "elembio/bases2fastq:2.4.0" not in nextflow_config_text

        project_a = tmpdir / "results" / "output" / "Project_A"
        project_b = tmpdir / "results" / "output" / "Project_B"
        project_a_fastq = project_a / "S1_S1_L001_R1_001.fastq.gz"
        project_b_fastq = project_b / "S2_S2_L001_R1_001.fastq.gz"
        assert project_a_fastq.is_file()
        assert project_b_fastq.is_file()
        assert not project_a_fastq.is_symlink()
        assert not project_b_fastq.is_symlink()
        assert not (tmpdir / "results" / "HLHGVBGYX").exists()
        project_a_qc = project_a / "qc" / "input" / "S1_fastqc.html"
        assert project_a_qc.is_file()
        assert not project_a_qc.is_symlink()
        assert project_a_qc.stat().st_nlink > 1
        assert (project_a / "qc" / "multiqc" / "multiqc_report.html").exists()
        assert (project_a / ".linkar" / "meta.json").exists()
        assert (tmpdir / "results" / "empty_fastq_report.csv").exists()
        assert (tmpdir / "results" / "manifest_lint_report.csv").exists()
        meta = json.loads((project_a / ".linkar" / "meta.json").read_text(encoding="utf-8"))
        assert meta["template"] == "nfcore_demultiplex"
        assert len(meta["outputs"]["demux_fastq_files"]) == 2
        assert (tmpdir / "results" / "software_versions.json").exists()


def test_aviti_defaults_to_run_manifest_and_bases2fastq() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-demux-aviti-") as tmp:
        tmpdir = Path(tmp)
        copy_runtime_template(tmpdir)
        fake_bin = make_fake_runtime_bin(tmpdir)
        raw_run_dir = write_aviti_run(tmpdir)
        env = {
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            "RAW_RUN_DIR": str(raw_run_dir),
            "NFCORE_ARGS_LOG": str(tmpdir / "args.log"),
            "LINKAR_PACK_ROOT": str(PACK_ROOT),
        }
        completed = run_template(tmpdir, env)
        assert completed.returncode == 0, completed.stderr
        run_params = (tmpdir / "config" / "run_params.env").read_text(encoding="utf-8")
        assert "PLATFORM=aviti" in run_params
        assert "DEMULTIPLEXER=bases2fastq" in run_params
        assert "SKIP_TOOLS=multiqc" in run_params
        assert "FLOWCELL_ID=AVITI_RUN_001" in run_params
        assert "DEMUX_CPUS=''" in run_params
        assert "FALCO_CPUS=''" in run_params
        flowcell_samplesheet = (tmpdir / "flowcell_samplesheet.csv").read_text(encoding="utf-8")
        assert flowcell_samplesheet.startswith("[Run]\n")
        assert "# ExampleSample_1,DefaultProject,AAAAAAAAAA,GGGGGGGGGG" in flowcell_samplesheet
        assert "# ExampleSample_1,DefaultProject,TTTTTTTTTT,CCCCCCCCCC" in flowcell_samplesheet
        lint_report = (tmpdir / "results" / "manifest_lint_report.csv").read_text(encoding="utf-8")
        assert "ExampleSample_1" not in lint_report
        args_text = (tmpdir / "args.log").read_text(encoding="utf-8")
        assert "--demultiplexer bases2fastq" in args_text


def test_cpu_overrides_are_written_to_runtime_env() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-demux-cpus-") as tmp:
        tmpdir = Path(tmp)
        copy_runtime_template(tmpdir)
        raw_run_dir = write_aviti_run(tmpdir)
        env = {
            "RAW_RUN_DIR": str(raw_run_dir),
            "LINKAR_PACK_ROOT": str(PACK_ROOT),
            "MAX_CPUS": "32",
            "MAX_MEMORY": "128GB",
            "DEMUX_CPUS": "24",
            "FALCO_CPUS": "6",
        }
        completed = subprocess.run(
            ["python3", "run.py", "--prepare"],
            cwd=tmpdir,
            env={**os.environ, **env},
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        run_params = (tmpdir / "config" / "run_params.env").read_text(encoding="utf-8")
        assert "MAX_CPUS=32" in run_params
        assert "MAX_MEMORY=128.GB" in run_params
        assert "DEMUX_CPUS=24" in run_params
        assert "FALCO_CPUS=6" in run_params


class FakeTemplate:
    def __init__(self, root: Path) -> None:
        self.root = str(root)


class FakeContext:
    def __init__(self, root: Path, resolved_params: dict[str, object]) -> None:
        self.template = FakeTemplate(root)
        self.resolved_params = resolved_params


def test_bindings_are_registered_and_aviti_manifest_resolves() -> None:
    pack_data = yaml.safe_load((PACK_ROOT / "linkar_pack.yaml").read_text(encoding="utf-8"))
    params = pack_data["templates"]["nfcore_demultiplex"]["params"]
    assert params["flowcell_samplesheet"]["function"] == "get_nfcore_demultiplex_flowcell_samplesheet"
    assert params["max_cpus"]["function"] == "get_host_max_cpus"
    assert params["max_memory"]["function"] == "get_host_max_memory"
    assert pack_data["templates"]["nfcore_demultiplex"]["outdir"]["function"] == "get_nfcore_demultiplex_render_outdir"

    with tempfile.TemporaryDirectory(prefix="linkar-nfcore-demux-binding-") as tmp:
        tmpdir = Path(tmp)
        raw_run_dir = write_aviti_run(tmpdir)
        resolve = load_function("get_nfcore_demultiplex_flowcell_samplesheet")
        value = resolve(
            FakeContext(
                TEMPLATE_DIR,
                {
                    "raw_run_dir": str(raw_run_dir),
                    "platform": "auto",
                    "demultiplexer": "auto",
                    "flowcell_samplesheet": "",
                },
            )
        )
        assert value == str((raw_run_dir / "RunManifest.csv").resolve())


def test_illumina_binding_uses_flowcell_api_before_agendo() -> None:
    module = load_function_module("get_nfcore_demultiplex_flowcell_samplesheet")

    class FakeApi:
        API_BASE_FLOWCELL = "https://example.test/flowcell/"
        API_BASE_REQUEST = "https://example.test/request/"

        def __init__(self) -> None:
            self.calls: list[str] = []
            self.cache = Path(tempfile.mkdtemp(prefix="nfcore-demux-api-cache-"))

        def _build_auth_header(self) -> str:
            return "Basic token"

        def _parse_flowcell_id(self, bcl_dir: str) -> str:
            return "H7CGGBGYX"

        def _extract_not_found_detail(self, _exc: HTTPError) -> str:
            return "not found"

        def _cache_root(self) -> Path:
            return self.cache

        def _fetch(self, url: str, _auth_header: str) -> bytes:
            self.calls.append(url)
            return b"[Header]\nIEMFileVersion,4\n"

    fake = FakeApi()
    original = module._load_api_module
    module._load_api_module = lambda: fake
    try:
        value = module.resolve(
            FakeContext(
                TEMPLATE_DIR,
                {
                    "raw_run_dir": "/data/run/260608_NB501289_0999_AH7CGGBGYX",
                    "platform": "illumina",
                    "demultiplexer": "bclconvert",
                    "flowcell_samplesheet": "",
                    "agendo_id": "6101",
                    "use_api_samplesheet": True,
                },
            )
        )
        assert Path(value).read_text(encoding="utf-8") == "[Header]\nIEMFileVersion,4\n"
        assert fake.calls == ["https://example.test/flowcell/H7CGGBGYX"]
    finally:
        module._load_api_module = original
        shutil.rmtree(fake.cache, ignore_errors=True)


def test_illumina_binding_falls_back_to_agendo_after_flowcell_404() -> None:
    module = load_function_module("get_nfcore_demultiplex_flowcell_samplesheet")

    class FakeApi:
        API_BASE_FLOWCELL = "https://example.test/flowcell/"
        API_BASE_REQUEST = "https://example.test/request/"

        def __init__(self) -> None:
            self.calls: list[str] = []
            self.cache = Path(tempfile.mkdtemp(prefix="nfcore-demux-api-cache-"))

        def _build_auth_header(self) -> str:
            return "Basic token"

        def _parse_flowcell_id(self, bcl_dir: str) -> str:
            return "H7CGGBGYX"

        def _extract_not_found_detail(self, _exc: HTTPError) -> str:
            return "not found"

        def _cache_root(self) -> Path:
            return self.cache

        def _fetch(self, url: str, _auth_header: str) -> bytes:
            self.calls.append(url)
            if "/flowcell/" in url:
                raise HTTPError(url, 404, "not found", hdrs=None, fp=None)
            return b"[Header]\nIEMFileVersion,4\n"

    fake = FakeApi()
    original = module._load_api_module
    module._load_api_module = lambda: fake
    try:
        value = module.resolve(
            FakeContext(
                TEMPLATE_DIR,
                {
                    "raw_run_dir": "/data/run/260608_NB501289_0999_AH7CGGBGYX",
                    "platform": "illumina",
                    "demultiplexer": "bclconvert",
                    "flowcell_samplesheet": "",
                    "agendo_id": "6101",
                    "use_api_samplesheet": True,
                },
            )
        )
        assert Path(value).read_text(encoding="utf-8") == "[Header]\nIEMFileVersion,4\n"
        assert fake.calls == [
            "https://example.test/flowcell/H7CGGBGYX",
            "https://example.test/request/6101",
        ]
    finally:
        module._load_api_module = original
        shutil.rmtree(fake.cache, ignore_errors=True)


def test_render_outdir_shortens_yyyy_mm_dd_prefix() -> None:
    resolve = load_function("get_nfcore_demultiplex_render_outdir")
    value = resolve(
        FakeContext(
            TEMPLATE_DIR,
            {
                "raw_run_dir": "/data/raw/aviti/AV261102/20260609_AV261102_InstallPV-SideA",
            },
        )
    )
    assert value == "/data/fastq/260609_AV261102_InstallPV-SideA"


def main() -> None:
    test_illumina_run_script()
    test_aviti_defaults_to_run_manifest_and_bases2fastq()
    test_cpu_overrides_are_written_to_runtime_env()
    test_bindings_are_registered_and_aviti_manifest_resolves()
    test_illumina_binding_uses_flowcell_api_before_agendo()
    test_illumina_binding_falls_back_to_agendo_after_flowcell_404()
    test_render_outdir_shortens_yyyy_mm_dd_prefix()
    print("nfcore_demultiplex template test passed")


if __name__ == "__main__":
    main()
