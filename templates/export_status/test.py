#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/export/status/job-123":
            self.send_error(404)
            return
        body = json.dumps(
            {
                "job_id": "job-123",
                "status": "completed",
                "main_report": "https://example.org/export/123",
                "final_path": "/exports/project_123",
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
        results_dir = Path(tmpdir) / "results"
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TEMPLATE_DIR / "run.py"),
                    "--results-dir",
                    str(results_dir),
                    "--job-id",
                    "job-123",
                    "--export-engine-api-url",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert "completed" in completed.stdout
            payload = json.loads((results_dir / "export_status.json").read_text(encoding="utf-8"))
            assert payload["job_id"] == "job-123"
            assert payload["final_path"] == "/exports/project_123"
            assert (results_dir / "export_job_id.txt").read_text(encoding="utf-8").strip() == "job-123"
        finally:
            server.shutdown()
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
