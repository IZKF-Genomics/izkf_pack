#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import html
import yaml


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def tier_info(name: str, results_dir: Path, report_path: Path) -> dict:
    info = load_yaml(results_dir / "run_info.yaml")
    return {
        "tier": name,
        "status": str(info.get("status", "not_run")),
        "message": str(info.get("message", "")),
        "report_exists": report_path.exists(),
        "report_path": report_path.relative_to(ROOT).as_posix() if report_path.exists() else "",
    }


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tiers = [
        tier_info("Tier 1 Quick Preview", ROOT / "tier1_quick_preview" / "results", ROOT / "tier1_quick_preview" / "reports" / "01_quick_preview.html"),
        tier_info("Tier 2 Refinement", ROOT / "tier2_refinement" / "results", ROOT / "tier2_refinement" / "reports" / "02_refinement.html"),
        tier_info("Tier 3 Formal Annotation", ROOT / "tier3_formal_annotation" / "results", ROOT / "tier3_formal_annotation" / "reports" / "03_formal_annotation.html"),
    ]

    next_step = "Run Tier 1 to generate the first preview report."
    if tiers[0]["status"] not in {"", "not_run"} and tiers[1]["status"] in {"", "not_run"}:
        next_step = "Run Tier 2 to refine the preview with marker-backed evidence."
    elif tiers[1]["status"] not in {"", "not_run"} and tiers[2]["status"] in {"", "not_run"}:
        next_step = "Enable a formal method in Tier 3 only if a suitable reference or model exists."
    elif tiers[2]["status"] == "complete":
        next_step = "Review Tier 3 outputs and keep unresolved clusters as Unknown when confidence remains limited."

    tier_rows = []
    for tier in tiers:
        link = f"<a href=\"../{html.escape(tier['report_path'])}\">open report</a>" if tier["report_exists"] else "report not available yet"
        tier_rows.append(
            "<tr>"
            f"<td>{html.escape(tier['tier'])}</td>"
            f"<td>{html.escape(tier['status'])}</td>"
            f"<td>{html.escape(tier['message'])}</td>"
            f"<td>{link}</td>"
            "</tr>"
        )

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>scrna_annotate Workflow Overview</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem auto; max-width: 1100px; line-height: 1.5; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    .box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
    code {{ background: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>scrna_annotate Workflow Overview</h1>
  <p>This page summarizes the current state of the rebuilt tiered annotation workflow.</p>
  <div class="box">
    <h2>How To Use This Workflow</h2>
    <p>Start with Tier 1 for a low-setup preview, move to Tier 2 for evidence-backed refinement, and only enable Tier 3 when a formal reference-aware method is justified.</p>
  </div>
  <div class="box">
    <h2>Tier Status</h2>
    <table>
      <thead><tr><th>Tier</th><th>Status</th><th>Message</th><th>Report</th></tr></thead>
      <tbody>
        {''.join(tier_rows)}
      </tbody>
    </table>
  </div>
  <div class="box">
    <h2>Recommended Next Step</h2>
    <p>{html.escape(next_step)}</p>
  </div>
</body>
</html>
"""
    (REPORTS_DIR / "00_overview.html").write_text(html_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
