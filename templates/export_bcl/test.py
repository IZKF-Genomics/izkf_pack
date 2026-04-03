#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/export":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.payload = payload  # type: ignore[attr-defined]
        body = json.dumps({"job_id": "job-456"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/export/final_message/job-456":
            self.send_error(404)
            return
        body = json.dumps(
            {
                "status": "completed",
                "main_report": "https://example.org/bcl",
                "final_path": "/exports/bcl",
                "formatted_message": "**BCL export complete**",
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        run_dir = root / "bcl_run"
        results_dir = root / "results"
        run_dir.mkdir()
        (run_dir / "RunInfo.xml").write_text("<xml/>\n", encoding="utf-8")

        dry = subprocess.run(
            [
                "python",
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results_dir),
                "--run-dir",
                str(run_dir),
                "--dry-run",
                "true",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Dry Run" in dry.stdout
        assert (results_dir / "export_job_spec.redacted.json").exists()
        assert not (run_dir / ".linkar").exists()

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            submit = subprocess.run(
                [
                    "python",
                    str(TEMPLATE_DIR / "run.py"),
                    "--results-dir",
                    str(results_dir),
                    "--run-dir",
                    str(run_dir),
                    "--export-engine-api-url",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert "job-456" in submit.stdout
            summary = json.loads((results_dir / "export_bcl_summary.json").read_text(encoding="utf-8"))
            assert summary["job_id"] == "job-456"
            assert summary["final_path"] == "/exports/bcl"
            assert (results_dir / "export_response.json").exists()
            assert (results_dir / "export_final_message.json").exists()
            assert not (run_dir / ".linkar").exists()
        finally:
            server.shutdown()
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
