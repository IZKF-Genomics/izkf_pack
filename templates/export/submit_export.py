#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit a prepared export_job_spec.json to the export engine.")
    parser.add_argument("--results-dir", default="./results")
    parser.add_argument("--api-url", required=True)
    return parser.parse_args()


def endpoint(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    return base if base.endswith("/export") else f"{base}/export"


def final_message_endpoint(export_url: str, job_id: str) -> str:
    if export_url.endswith("/export"):
        return f"{export_url.rsplit('/export', 1)[0]}/export/final_message/{job_id}"
    return f"{export_url}/final_message/{job_id}"


def strip_markdown(text: str) -> str:
    text = re.sub(r"^[#>\-\*]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
    return text.strip()


def fetch_final_message(url: str) -> dict[str, object]:
    req = Request(url=url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body) if body else {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    spec_path = results_dir / "export_job_spec.json"
    if not spec_path.exists():
        raise SystemExit(f"export spec not found: {spec_path}")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    export_url = endpoint(args.api_url)

    req = Request(
        url=export_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    response = json.loads(body) if body else {}
    if not isinstance(response, dict):
        raise SystemExit("export engine returned a non-object response")
    job_id = str(response.get("job_id") or "").strip()
    if not job_id:
        raise SystemExit("export engine response did not include job_id")

    status_payload: dict[str, object] = {"job_id": job_id, "submission": response}
    final_message_text = ""
    final_path = ""
    try:
        final_payload = fetch_final_message(final_message_endpoint(export_url, job_id))
        status_payload["final_message"] = final_payload
        final_message_text = strip_markdown(str(final_payload.get("message") or ""))
        final_path = str(final_payload.get("final_path") or "").strip()
    except HTTPError as exc:
        status_payload["final_message_error"] = f"{exc.code}: {exc.reason}"
    except Exception as exc:
        status_payload["final_message_error"] = str(exc)

    (results_dir / "export_submission.json").write_text(
        json.dumps(status_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    (results_dir / "export_job_id.txt").write_text(job_id + "\n", encoding="utf-8")
    (results_dir / "export_final_message.txt").write_text(final_message_text + ("\n" if final_message_text else ""), encoding="utf-8")
    (results_dir / "export_final_path.txt").write_text(final_path + ("\n" if final_path else ""), encoding="utf-8")
    print(f"[info] export job submitted: {job_id}")
    if final_message_text:
        print(final_message_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
