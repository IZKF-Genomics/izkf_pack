#!/usr/bin/env python3
from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent


def copy_workspace(tmpdir: Path) -> Path:
    workspace = tmpdir / "methylation_array_analysis"
    shutil.copytree(TEMPLATE_DIR, workspace)
    return workspace


def test_build_inputs(workspace: Path) -> None:
    results_dir = workspace / "results"
    project_dir = workspace.parent / "260302_ProjectA"
    project_dir.mkdir()
    subprocess.run(
        [
            sys.executable,
            str(workspace / "build_dnam_inputs.py"),
            "--workspace-dir",
            str(workspace),
            "--project-dir",
            str(project_dir),
            "--results-dir",
            str(results_dir),
            "--authors",
            "A, B",
        ],
        check=True,
    )
    inputs_text = (workspace / "dnam_inputs.R").read_text(encoding="utf-8")
    assert 'project_name <- "260302_ProjectA"' in inputs_text
    run_info = yaml.safe_load((results_dir / "run_info.yaml").read_text(encoding="utf-8"))
    assert run_info["params"]["project_name"] == "260302_ProjectA"
    assert run_info["params"]["authors"] == "A, B"


def test_registry_scripts(workspace: Path) -> None:
    local_dir = workspace / "data" / "inbox" / "dataset_local"
    local_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("Red", "Grn"):
        (local_dir / f"1234567890_R01C01_{suffix}.idat").write_text("stub\n", encoding="utf-8")
        (local_dir / f"1234567890_R02C01_{suffix}.idat").write_text("stub\n", encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(workspace / "scripts" / "register_local.py"),
            "--dataset-id",
            "dataset_local",
            "--path",
            str(local_dir),
            "--array-type",
            "EPIC_V2",
        ],
        cwd=workspace,
        check=True,
    )
    subprocess.run([sys.executable, str(workspace / "scripts" / "sync_samples.py")], cwd=workspace, check=True)

    with (workspace / "config" / "samples.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert any(row["dataset_id"] == "dataset_local" for row in rows)
    assert any(row["SentrixPosition"] == "R01C01" for row in rows)

    subprocess.run([sys.executable, str(workspace / "scripts" / "preflight_inputs.py")], cwd=workspace, check=True)
    assert (workspace / "results" / "tables" / "idat_preflight.csv").exists()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="linkar-methyl-array-template-test-") as tmp:
        workspace = copy_workspace(Path(tmp))
        test_build_inputs(workspace)
        test_registry_scripts(workspace)

    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    constructor_text = (TEMPLATE_DIR / "DNAm_constructor.R").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    assert "id: methylation_array_analysis" in template_text
    assert "study_name" not in template_text
    assert "build_dnam_inputs.py" in run_sh_text
    assert 'source("dnam_inputs.R")' in constructor_text
    assert "default_comparisons_from_samples" in constructor_text
    assert "comparison_report.qmd" in (TEMPLATE_DIR / "DNAm_functions.R").read_text(encoding="utf-8")
    assert "config/datasets.toml" in readme_text
    assert "DNAm_constructor.R" in readme_text
    print("methylation_array_analysis template test passed")


if __name__ == "__main__":
    main()
