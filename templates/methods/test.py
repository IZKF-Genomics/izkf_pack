#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        project_dir = root / "project"
        results_dir = root / "results"
        run_dir = project_dir / "analysis"
        (run_dir / ".linkar").mkdir(parents=True)
        (run_dir / ".linkar" / "runtime.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "returncode": 0,
                    "command": ["run.sh"],
                    "duration_seconds": 1.2,
                }
            ),
            encoding="utf-8",
        )
        results_source = run_dir / "results"
        results_source.mkdir()
        (results_source / "software_versions.json").write_text(
            json.dumps(
                {
                    "software": [
                        {
                            "name": "cellranger-atac",
                            "version": "cellranger-atac 2.2.0",
                            "source": "command",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        project_dir.mkdir(exist_ok=True)
        (project_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "example_project_001",
                    "author": {"name": "Example User", "organization": "Example Org"},
                    "templates": [
                        {
                            "id": "cellranger_atac",
                            "template_version": "0.1.0",
                            "instance_id": "cellranger_atac_001",
                            "path": str(run_dir),
                            "outputs": {
                                "results_dir": str(results_source),
                                "software_versions": str(results_source / "software_versions.json"),
                            },
                            "params": {
                                "reference": "/refs/example_reference",
                                "run_aggr": True,
                                "localcores": 8,
                            },
                        }
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results_dir),
                "--project-dir",
                str(project_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "methods_long.md" in completed.stdout
        long_text = (results_dir / "methods_long.md").read_text(encoding="utf-8")
        short_text = (results_dir / "methods_short.md").read_text(encoding="utf-8")
        refs = (results_dir / "methods_references.md").read_text(encoding="utf-8")
        context = yaml.safe_load((results_dir / "methods_context.yaml").read_text(encoding="utf-8"))
        assert "Single-cell ATAC-seq processing" in long_text
        assert "example_reference" in long_text
        assert "cellranger-atac 2.2.0" in long_text
        assert "1 recorded workflow" in short_text
        assert "Cell Ranger ATAC" in refs
        assert context["runs"][0]["template"] == "cellranger_atac"
        assert context["runs"][0]["software_versions"][0]["name"] == "cellranger-atac"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
