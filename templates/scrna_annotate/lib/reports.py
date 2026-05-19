from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def render_qmd(qmd_path: Path, warnings: list[str]) -> Path | None:
    if shutil.which("quarto") is None:
        warnings.append("Quarto is not available; report.qmd was written but was not rendered to HTML.")
        return None
    try:
        subprocess.run(["quarto", "render", qmd_path.name, "--to", "html", "--no-clean"], cwd=qmd_path.parent, check=True)
    except Exception as exc:
        warnings.append(f"Quarto render failed; report.qmd was written but HTML was not rendered: {exc}")
        return None
    html_path = qmd_path.with_suffix(".html")
    return html_path if html_path.exists() else None
