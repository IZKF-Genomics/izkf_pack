#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


def make_fake_pixi_bin(root: Path) -> Path:
    bin_dir = root / "bin-pixi"
    bin_dir.mkdir()
    pixi = bin_dir / "pixi"
    pixi.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == \"install\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" != \"run\" || \"${2:-}\" != \"python\" || \"${3:-}\" != \"-m\" || \"${4:-}\" != \"demux_pipeline.cli\" ]]; then\n"
        "  echo \"unsupported fake pixi invocation: $*\" >&2\n"
        "  exit 1\n"
        "fi\n"
        "shift 4\n"
        "python - \"$@\" <<'PY'\n"
        "from __future__ import annotations\n"
        "import argparse\n"
        "import json\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--outdir', required=True, type=Path)\n"
        "parser.add_argument('--bcl_dir', required=True, type=Path)\n"
        "parser.add_argument('--samplesheet', required=True, type=Path)\n"
        "parser.add_argument('--qc-tool', required=True)\n"
        "parser.add_argument('--contamination-tool', default='none')\n"
        "parser.add_argument('--threads', required=True, type=int)\n"
        "parser.add_argument('--run-name', default='')\n"
        "parser.add_argument('--kraken-db', default='')\n"
        "parser.add_argument('--bracken-db', default='')\n"
        "parser.add_argument('--fastq-screen-conf', default='')\n"
        "parser.add_argument('--output-contract-file', required=True, type=Path)\n"
        "args = parser.parse_args()\n"
        "args.outdir.mkdir(parents=True, exist_ok=True)\n"
        "(args.outdir / 'output').mkdir(exist_ok=True)\n"
        "(args.outdir / 'output' / 'sample_R1.fastq.gz').write_text('demux\\n', encoding='utf-8')\n"
        "if 'fastqc' in args.qc_tool:\n"
        "    fastqc_dir = args.outdir / 'fastqc'\n"
        "    fastqc_dir.mkdir(exist_ok=True)\n"
        "    (fastqc_dir / 'sample_fastqc.html').write_text('<html>fastqc</html>\\n', encoding='utf-8')\n"
        "if 'fastp' in args.qc_tool:\n"
        "    fastp_dir = args.outdir / 'fastp'\n"
        "    fastp_dir.mkdir(exist_ok=True)\n"
        "    (fastp_dir / 'sample.html').write_text('<html>fastp</html>\\n', encoding='utf-8')\n"
        "    (fastp_dir / 'sample.json').write_text('{}\\n', encoding='utf-8')\n"
        "    passthrough = args.outdir / 'fastp_passthrough'\n"
        "    passthrough.mkdir(exist_ok=True)\n"
        "    (passthrough / 'sample_R1.fastq.gz').write_text('fastp\\n', encoding='utf-8')\n"
        "if 'falco' in args.qc_tool:\n"
        "    falco_dir = args.outdir / 'falco' / 'sample_R1'\n"
        "    falco_dir.mkdir(parents=True, exist_ok=True)\n"
        "    (falco_dir / 'report.html').write_text('<html>falco</html>\\n', encoding='utf-8')\n"
        "if args.contamination_tool != 'none':\n"
        "    contamination = args.outdir / 'contamination'\n"
        "    contamination.mkdir(exist_ok=True)\n"
        "    (contamination / 'summary.txt').write_text(args.contamination_tool + '\\n', encoding='utf-8')\n"
        "multiqc_dir = args.outdir / 'multiqc'\n"
        "multiqc_dir.mkdir(exist_ok=True)\n"
        "(multiqc_dir / 'multiqc_report.html').write_text('<html>multiqc</html>\\n', encoding='utf-8')\n"
        "(args.outdir / 'samples.tsv').write_text('sample\\tR1\\t\\n', encoding='utf-8')\n"
        "pipeline_dir = args.outdir / '.pipeline' / 'run-001'\n"
        "pipeline_dir.mkdir(parents=True, exist_ok=True)\n"
        "(pipeline_dir / 'run_summary.json').write_text(json.dumps({'run_name': args.run_name, 'threads': args.threads}) + '\\n', encoding='utf-8')\n"
        "payload = {\n"
        "    'outdir': str(args.outdir),\n"
        "    'outputs': {\n"
        "        'samples_tsv': str(args.outdir / 'samples.tsv'),\n"
        "        'qc_dir': str(args.outdir / 'fastqc') if (args.outdir / 'fastqc').exists() else None,\n"
        "        'contamination_dir': str(args.outdir / 'contamination') if (args.outdir / 'contamination').exists() else None,\n"
        "        'multiqc_report': str(args.outdir / 'multiqc' / 'multiqc_report.html'),\n"
        "        'run_summary': str(pipeline_dir / 'run_summary.json'),\n"
        "    },\n"
        "}\n"
        "args.output_contract_file.write_text(json.dumps(payload, indent=2) + '\\n', encoding='utf-8')\n"
        "PY\n"
    )
    pixi.chmod(0o755)
    return bin_dir


def make_fake_git_bin(root: Path) -> Path:
    bin_dir = root / "bin-git"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" != \"clone\" ]]; then\n"
        "  echo \"unsupported fake git invocation: $*\" >&2\n"
        "  exit 1\n"
        "fi\n"
        "target=\"${@: -1}\"\n"
        "mkdir -p \"${target}/demux_pipeline\"\n"
        "printf '# fake upstream\\n' > \"${target}/pixi.toml\"\n"
        "printf '__all__ = []\\n' > \"${target}/demux_pipeline/__init__.py\"\n"
        "printf 'repo=%s\\n' \"${3:-}\" > \"${target}/CLONED_FROM.txt\"\n",
        encoding="utf-8",
    )
    git.chmod(0o755)
    return bin_dir


def make_fake_demux_bin(root: Path) -> Path:
    bin_dir = root / "bin-demux"
    bin_dir.mkdir()
    for name in ("bcl-convert", "bcl_convert"):
        path = bin_dir / name
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
        path.chmod(0o755)
    return bin_dir


def make_demux_inputs(root: Path) -> tuple[Path, Path]:
    demux_input = root / "demux_input"
    demux_input.mkdir()
    samplesheet = root / "SampleSheet.csv"
    samplesheet.write_text(
        "[Header]\n"
        "IEMFileVersion,4\n"
        "[Reads]\n"
        "151\n"
        "151\n"
        "[Data]\n"
        "Sample_ID,Sample_Name\n"
        "S1,S1\n"
    )
    return demux_input, samplesheet


def run_case(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        ["bash", "run.sh"],
        cwd=TEMPLATE_DIR,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-demultiplex-test-") as tmp:
        tmpdir = Path(tmp)
        fake_pixi_bin = make_fake_pixi_bin(tmpdir)
        fake_demux_bin = make_fake_demux_bin(tmpdir)
        fake_git_bin = make_fake_git_bin(tmpdir)
        demux_input, samplesheet = make_demux_inputs(tmpdir)

        results_dir = tmpdir / "demux-results"
        run_script = tmpdir / "run.sh"
        run_script.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "\n"
            "LINKAR_RESULTS_DIR=\"${LINKAR_RESULTS_DIR:?}\"\n"
            "BCL_DIR=\"${BCL_DIR:?}\"\n"
            "SAMPLESHEET=\"${SAMPLESHEET:?}\"\n"
            "QC_TOOL=\"${QC_TOOL:?}\"\n"
            "CONTAMINATION_TOOL=\"${CONTAMINATION_TOOL:?}\"\n"
            "THREADS=\"${THREADS:?}\"\n"
            "RUN_NAME=\"${RUN_NAME:-}\"\n"
            "KRAKEN_DB=\"${KRAKEN_DB:-}\"\n"
            "BRACKEN_DB=\"${BRACKEN_DB:-}\"\n"
            "FASTQ_SCREEN_CONF=\"${FASTQ_SCREEN_CONF:-}\"\n"
            "upstream_repo_url=\"https://github.com/MoSafi2/demultiplexing_prefect\"\n"
            "upstream_repo_dir=\"./demultiplexing_prefect\"\n"
            "rm -rf \"${upstream_repo_dir}\"\n"
            "git clone --depth 1 \"${upstream_repo_url}\" \"${upstream_repo_dir}\"\n"
            "pushd \"${upstream_repo_dir}\" >/dev/null\n"
            "pixi run python -m demux_pipeline.cli \\\n"
            "  --outdir \"${LINKAR_RESULTS_DIR}\" \\\n"
            "  --bcl_dir \"${BCL_DIR}\" \\\n"
            "  --samplesheet \"${SAMPLESHEET}\" \\\n"
            "  --qc-tool \"${QC_TOOL}\" \\\n"
            "  --contamination-tool \"${CONTAMINATION_TOOL}\" \\\n"
            "  --threads \"${THREADS}\" \\\n"
            "  --output-contract-file \"${LINKAR_RESULTS_DIR}/template_outputs.json\" \\\n"
            "  ${RUN_NAME:+--run-name \"${RUN_NAME}\"} \\\n"
            "  ${KRAKEN_DB:+--kraken-db \"${KRAKEN_DB}\"} \\\n"
            "  ${BRACKEN_DB:+--bracken-db \"${BRACKEN_DB}\"} \\\n"
            "  ${FASTQ_SCREEN_CONF:+--fastq-screen-conf \"${FASTQ_SCREEN_CONF}\"}\n"
            "popd >/dev/null\n",
            encoding="utf-8",
        )
        run_script.chmod(0o755)
        env = {
            "QC_TOOL": "fastqc,fastp",
            "THREADS": "2",
            "RUN_NAME": "demux-test",
            "BCL_DIR": str(demux_input),
            "SAMPLESHEET": str(samplesheet),
            "CONTAMINATION_TOOL": "kraken",
            "KRAKEN_DB": str(tmpdir / "kraken_db"),
            "BRACKEN_DB": "",
            "FASTQ_SCREEN_CONF": "",
            "LINKAR_OUTPUT_DIR": str(tmpdir / "demux-run"),
            "LINKAR_RESULTS_DIR": str(results_dir),
            "PATH": f"{fake_pixi_bin}:{fake_demux_bin}:{fake_git_bin}:{os.environ.get('PATH', '')}",
        }
        completed = subprocess.run(
            ["bash", str(run_script)],
            cwd=tmpdir,
            env={**os.environ, **env},
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert (results_dir / "output" / "sample_R1.fastq.gz").exists()
        assert (results_dir / "fastqc" / "sample_fastqc.html").exists()
        assert (results_dir / "fastp" / "sample.html").exists()
        assert (results_dir / "fastp" / "sample.json").exists()
        assert (results_dir / "fastp_passthrough" / "sample_R1.fastq.gz").exists()
        assert (results_dir / "multiqc" / "multiqc_report.html").exists()
        assert (results_dir / "samples.tsv").exists()

        contract = json.loads((results_dir / "template_outputs.json").read_text(encoding="utf-8"))
        assert contract["outputs"]["samples_tsv"] == str(results_dir / "samples.tsv")
        assert contract["outputs"]["contamination_dir"] == str(results_dir / "contamination")
        assert (tmpdir / "demultiplexing_prefect" / "demux_pipeline" / "__init__.py").exists()

        template_yaml = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
        assert 'git clone --depth 1 "${upstream_repo_url}" "${upstream_repo_dir}"' in template_yaml
        assert 'pixi run python -m demux_pipeline.cli' in template_yaml
        assert not (TEMPLATE_DIR / "demux_pipeline" / "cli.py").exists()
        assert not (TEMPLATE_DIR / "pixi.toml").exists()
        assert not (TEMPLATE_DIR / "pixi.lock").exists()

    print("demultiplex template test passed")


if __name__ == "__main__":
    main()
