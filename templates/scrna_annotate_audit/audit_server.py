#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


RUN_DIR = Path(__file__).resolve().parent
RESULTS_DIR = Path(__import__("os").environ.get("LINKAR_RESULTS_DIR", RUN_DIR / "results")).resolve()
CONFIG_DIR = RUN_DIR / "config"
DECISIONS_PATH = CONFIG_DIR / "final_annotation_decisions.csv"
FINAL_H5AD = RESULTS_DIR / "adata.final_annotated.h5ad"
FINAL_CLOUPE = RESULTS_DIR / "adata.final_annotated.cloupe"
DECISION_FIELDS = [
    "cluster_id",
    "suggested_label",
    "suggested_broad_label",
    "decision",
    "confidence",
    "agreement_level",
    "review_priority",
    "review_status",
    "final_label",
    "reviewer_note",
]


def load_run_module():
    spec = importlib.util.spec_from_file_location("scrna_annotate_audit_run", RUN_DIR / "run.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def normalized_decision_rows(payload: dict) -> list[dict[str, str]]:
    rows = payload.get("decisions")
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        raise ValueError("Expected JSON field 'decisions' as a list or object")
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cluster_id = str(row.get("cluster_id") or "").strip()
        if not cluster_id:
            continue
        normalized.append({field: str(row.get(field) or "") for field in DECISION_FIELDS})
    if not normalized:
        raise ValueError("No decision rows with cluster_id were provided")
    normalized.sort(key=lambda row: (0, int(row["cluster_id"])) if row["cluster_id"].isdigit() else (1, row["cluster_id"]))
    return normalized


def save_decisions(payload: dict) -> dict:
    rows = normalized_decision_rows(payload)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with DECISIONS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DECISION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return {"saved": True, "rows": len(rows), "path": str(DECISIONS_PATH)}


def write_final_h5ad() -> dict:
    run = load_run_module()
    params = run.load_params()
    aliases = run.load_label_aliases(run.resolve_path(params["label_aliases"], base=RUN_DIR))
    draft_rows = run.read_csv_dicts(RESULTS_DIR / "tables" / "final_annotation_decisions_draft.csv")
    final_rows, source, warnings = run.apply_final_decisions(draft_rows, DECISIONS_PATH, aliases)
    cards = json.loads((RESULTS_DIR / "annotation_audit_cards.json").read_text(encoding="utf-8"))
    final_by_cluster = {str(row["cluster_id"]): row for row in final_rows}
    final_cards = run.attach_final_decisions(cards, final_by_cluster, source)
    run.write_csv(RESULTS_DIR / "tables" / "final_annotation_decisions_applied.csv", final_rows, DECISION_FIELDS)
    run.write_json(RESULTS_DIR / "annotation_audit_cards.json", final_cards)
    input_h5ad = Path(str(json.loads((RESULTS_DIR / "annotation_audit.json").read_text(encoding="utf-8")).get("input", {}).get("h5ad") or ""))
    if not input_h5ad.exists():
        input_h5ad = run.resolve_input_h5ad(params, [], warnings)
    run.write_final_h5ad(input_h5ad, FINAL_H5AD, params["cluster_key"], final_cards, params, warnings)
    cloupe_written = False
    if run.bool_param(params.get("write_cloupe", True)):
        cloupe_written = run.write_cloupe(FINAL_H5AD, FINAL_CLOUPE, params, warnings)
    return {
        "written": True,
        "path": str(FINAL_H5AD),
        "cloupe_written": cloupe_written,
        "cloupe_path": str(FINAL_CLOUPE),
        "decision_source": source,
        "warnings": warnings,
    }


def safe_file_path(path: str) -> Path | None:
    parsed = unquote(urlparse(path).path)
    if parsed == "/":
        parsed = "/results/report.html"
    rel = parsed.lstrip("/")
    candidate = (RUN_DIR / rel).resolve()
    try:
        candidate.relative_to(RUN_DIR)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


class AuditHandler(BaseHTTPRequestHandler):
    server_version = "AnnotationAuditServer/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[scrna_annotate_audit_api] {self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            write_json(
                self,
                200,
                {
                    "ok": True,
                    "api": "scrna_annotate_audit",
                    "run_dir": str(RUN_DIR),
                    "results_dir": str(RESULTS_DIR),
                    "decisions_csv": str(DECISIONS_PATH),
                    "decisions_exists": DECISIONS_PATH.exists(),
                    "final_h5ad": str(FINAL_H5AD),
                    "final_h5ad_exists": FINAL_H5AD.exists(),
                    "final_cloupe": str(FINAL_CLOUPE),
                    "final_cloupe_exists": FINAL_CLOUPE.exists(),
                },
            )
            return
        path = safe_file_path(parsed.path)
        if path is None:
            write_json(self, 404, {"ok": False, "error": "not found"})
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/save-decisions":
                result = save_decisions(read_json_body(self))
                write_json(self, 200, {"ok": True, **result})
                return
            if parsed.path == "/api/write-h5ad":
                result = write_final_h5ad()
                write_json(self, 200, {"ok": True, **result})
                return
            if parsed.path == "/api/save-and-write-h5ad":
                save_result = save_decisions(read_json_body(self))
                write_result = write_final_h5ad()
                write_json(self, 200, {"ok": True, "save": save_result, "write_h5ad": write_result})
                return
            write_json(self, 404, {"ok": False, "error": "unknown endpoint"})
        except Exception as exc:
            write_json(self, 500, {"ok": False, "error": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser(description="Temporary local API for scrna_annotate_audit")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Refusing to bind to a non-localhost address")
    server = ThreadingHTTPServer((args.host, args.port), AuditHandler)
    host, port = server.server_address
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / ".audit_server_url").write_text(f"http://{host}:{port}/results/report.html\n", encoding="utf-8")
    print("", flush=True)
    print("[scrna_annotate_audit] Annotation audit dashboard is ready.", flush=True)
    print(f"[scrna_annotate_audit] Open: http://{host}:{port}/results/report.html", flush=True)
    print("[scrna_annotate_audit] API actions enabled: save decisions, generate final h5ad.", flush=True)
    print("[scrna_annotate_audit] Press Ctrl-C to stop the temporary local API.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[scrna_annotate_audit] stopping temporary local API", flush=True)
    finally:
        server.server_close()
        try:
            (RESULTS_DIR / ".audit_server_url").unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
