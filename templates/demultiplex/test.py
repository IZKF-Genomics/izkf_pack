#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


def make_fake_upstream_repo(root: Path) -> Path:
    repo = root / "demultiplexing_prefect-source"
    repo.mkdir()
    (repo / "pixi.toml").write_text(
        "[workspace]\nname = \"demultiplexing_prefect\"\nchannels = [\"conda-forge\"]\nplatforms = [\"linux-64\", \"osx-64\", \"osx-arm64\"]\n"
    )
    (repo / "cli.py").write_text(
        "from __future__ import annotations\n"
        "import argparse\n"
        "from pathlib import Path\n\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--mode', required=True, choices=['demux', 'qc'])\n"
        "parser.add_argument('--qc-tool', required=True, choices=['fastqc', 'fastp', 'falco'])\n"
        "parser.add_argument('--threads', required=True, type=int)\n"
        "parser.add_argument('--outdir', required=True, type=Path)\n"
        "parser.add_argument('--run-name', default='')\n"
        "parser.add_argument('--bcl_dir', default='')\n"
        "parser.add_argument('--samplesheet', default='')\n"
        "parser.add_argument('--manifest-tsv', default='')\n"
        "parser.add_argument('--in-fastq-dir', default='')\n"
        "parser.add_argument('--contamination-tool', default='none')\n"
        "parser.add_argument('--kraken-db', default='')\n"
        "parser.add_argument('--bracken-db', default='')\n"
        "parser.add_argument('--fastq-screen-conf', default='')\n"
        "args = parser.parse_args()\n"
        "args.outdir.mkdir(parents=True, exist_ok=True)\n"
        "if args.mode == 'demux':\n"
        "    output_dir = args.outdir / 'output'\n"
        "    output_dir.mkdir(exist_ok=True)\n"
        "    (output_dir / 'sample_R1.fastq.gz').write_text('demux\\n')\n"
        "if args.qc_tool == 'fastqc':\n"
        "    fastqc_dir = args.outdir / 'fastqc'\n"
        "    fastqc_dir.mkdir(exist_ok=True)\n"
        "    (fastqc_dir / 'sample_fastqc.html').write_text('<html>fastqc</html>\\n')\n"
        "elif args.qc_tool == 'fastp':\n"
        "    fastp_dir = args.outdir / 'fastp'\n"
        "    fastp_dir.mkdir(exist_ok=True)\n"
        "    (fastp_dir / 'sample.html').write_text('<html>fastp</html>\\n')\n"
        "    (fastp_dir / 'sample.json').write_text('{}\\n')\n"
        "    passthrough = args.outdir / 'fastp_passthrough'\n"
        "    passthrough.mkdir(exist_ok=True)\n"
        "    (passthrough / 'sample_R1.fastq.gz').write_text('fastp\\n')\n"
        "else:\n"
        "    falco_dir = args.outdir / 'falco' / 'sample_R1'\n"
        "    falco_dir.mkdir(parents=True, exist_ok=True)\n"
        "    (falco_dir / 'report.html').write_text('<html>falco</html>\\n')\n"
        "multiqc_dir = args.outdir / 'multiqc'\n"
        "multiqc_dir.mkdir(exist_ok=True)\n"
        "(multiqc_dir / 'multiqc_report.html').write_text('<html>multiqc</html>\\n')\n"
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


def repo_head(repo: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def make_fake_pixi_bin(root: Path) -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    pixi = bin_dir / "pixi"
    pixi.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" != \"run\" || \"${2:-}\" != \"python\" ]]; then\n"
        "  echo \"unsupported fake pixi invocation: $*\" >&2\n"
        "  exit 1\n"
        "fi\n"
        "shift 2\n"
        "exec python \"$@\"\n"
    )
    pixi.chmod(0o755)
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


def make_qc_fastq_dir(root: Path) -> Path:
    qc_fastq = root / "qc_fastq"
    qc_fastq.mkdir()
    (qc_fastq / "sample_R1.fastq.gz").write_text("fake-fastq\n")
    return qc_fastq


class SamplesheetHandler(BaseHTTPRequestHandler):
    username = "demo-user"
    password = "demo-pass"
    samplesheet = (
        "[Header]\n"
        "IEMFileVersion,4\n"
        "[Reads]\n"
        "151\n"
        "151\n"
        "[Data]\n"
        "Sample_ID,Sample_Name\n"
        "S1,S1\n"
    ).encode("utf-8")

    def _authorized(self) -> bool:
        expected = f"Basic {__import__('base64').b64encode(f'{self.username}:{self.password}'.encode()).decode()}"
        return self.headers.get("Authorization") == expected

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self.send_response(401)
            self.end_headers()
            return
        if self.path.endswith("/FLOWCELL123"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.samplesheet)
            return
        if self.path.endswith("/REQ123"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.samplesheet)
            return
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"detail":"samplesheet not found"}')

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class SamplesheetServer:
    def __enter__(self) -> "SamplesheetServer":
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), SamplesheetHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)

    @property
    def flowcell_base(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/api/get/samplesheet/flowcell/"

    @property
    def request_base(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/api/get/samplesheet/request/"


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
        fake_repo = make_fake_upstream_repo(tmpdir)
        fake_revision = repo_head(fake_repo)
        fake_bin = make_fake_pixi_bin(tmpdir)
        demux_input, samplesheet = make_demux_inputs(tmpdir)
        qc_fastq = make_qc_fastq_dir(tmpdir)
        renamed_demux_input = tmpdir / "240101_RUN_AFLOWCELL123"
        demux_input.rename(renamed_demux_input)

        with SamplesheetServer() as api:
            demux_results = tmpdir / "demux-results"
            demux_env = {
                "MODE": "demux",
                "QC_TOOL": "fastqc",
                "THREADS": "2",
                "RUN_NAME": "demux-test",
                "BCL_DIR": str(renamed_demux_input),
                "SAMPLESHEET": "",
                "USE_API_SAMPLESHEET": "true",
                "AGENDO_ID": "REQ123",
                "FLOWCELL_ID": "",
                "MANIFEST_TSV": "",
                "IN_FASTQ_DIR": "",
                "CONTAMINATION_TOOL": "none",
                "KRAKEN_DB": "",
                "BRACKEN_DB": "",
                "FASTQ_SCREEN_CONF": "",
                "LINKAR_OUTPUT_DIR": str(tmpdir / "demux-run"),
                "LINKAR_RESULTS_DIR": str(demux_results),
                "DEMULTIPLEXING_PREFECT_REPO": str(fake_repo),
                "DEMULTIPLEXING_PREFECT_REVISION": fake_revision,
                "GF_API_NAME": SamplesheetHandler.username,
                "GF_API_PASS": SamplesheetHandler.password,
                "GF_API_BASE_FLOWCELL": api.flowcell_base,
                "GF_API_BASE_REQUEST": api.request_base,
                "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            }
            demux = run_case(demux_env)
            assert demux.returncode == 0, demux.stderr
            assert (demux_results / "output" / "sample_R1.fastq.gz").exists()
            assert (tmpdir / "demux-run" / "demultiplexing_prefect").is_dir()
            assert (tmpdir / "demux-run" / "samplesheet.csv").exists()

        qc_results = tmpdir / "qc-results"
        qc_env = {
            "MODE": "qc",
            "QC_TOOL": "fastp",
            "THREADS": "2",
            "RUN_NAME": "qc-test",
            "BCL_DIR": "",
            "SAMPLESHEET": "",
            "USE_API_SAMPLESHEET": "false",
            "AGENDO_ID": "",
            "FLOWCELL_ID": "",
            "MANIFEST_TSV": "",
            "IN_FASTQ_DIR": str(qc_fastq),
            "CONTAMINATION_TOOL": "none",
            "KRAKEN_DB": "",
            "BRACKEN_DB": "",
            "FASTQ_SCREEN_CONF": "",
            "LINKAR_OUTPUT_DIR": str(tmpdir / "qc-run"),
            "LINKAR_RESULTS_DIR": str(qc_results),
            "DEMULTIPLEXING_PREFECT_REPO": str(fake_repo),
            "DEMULTIPLEXING_PREFECT_REVISION": fake_revision,
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        }
        qc = run_case(qc_env)
        assert qc.returncode == 0, qc.stderr
        assert (qc_results / "fastp" / "sample.html").exists()
        assert (tmpdir / "qc-run" / "demultiplexing_prefect").is_dir()

    print("demultiplex template test passed")


if __name__ == "__main__":
    main()
