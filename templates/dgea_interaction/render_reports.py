#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, check=True, env=env)


def main() -> int:
    config = yaml.safe_load(Path("config/analysis.yaml").read_text())
    reports = Path("reports")
    comparisons = reports / "comparisons"
    comparisons.mkdir(parents=True, exist_ok=True)
    run(["quarto", "render", "DGEA_interaction_report.qmd", "--output", "DGEA_interaction_report.html", "--output-dir", str(reports)])
    for contrast in config["contrasts"]:
        contrast_id = contrast["id"]
        env = dict(os.environ, DGEA_CONTRAST_ID=contrast_id)
        run(["quarto", "render", "DGEA_contrast_report.qmd", "--output", f"{contrast_id}.html", "--output-dir", str(comparisons), "--no-clean"], env=env)
    expected = [reports / "DGEA_interaction_report.html", *[comparisons / f"{x['id']}.html" for x in config["contrasts"]]]
    bad = [str(path) for path in expected if not path.is_file() or path.stat().st_size < 20_000]
    if bad:
        raise SystemExit("Missing or unexpectedly small reports: " + ", ".join(bad))
    for path in (reports / "results", comparisons / "results"):
        if path.is_dir():
            import shutil
            shutil.rmtree(path)
    print(f"Rendered {len(expected)} self-contained HTML reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
