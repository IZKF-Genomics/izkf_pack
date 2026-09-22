#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
PACK_ROOT = TEMPLATE_DIR.parent.parent


class FakeProject:
    def __init__(self, root: Path, entries: list[dict]) -> None:
        self.root = root
        self.name = root.name
        self.data = {"templates": entries, "author": {"name": "Analyst"}}


class FakeContext:
    def __init__(self, root: Path, entries: list[dict]) -> None:
        self.project = FakeProject(root, entries)

    def latest_output(self, key: str, template_id: str | None = None):
        for entry in reversed(self.project.data["templates"]):
            if template_id is not None and entry.get("id") != template_id:
                continue
            value = (entry.get("outputs") or {}).get(key)
            if value:
                return value
        return None


def load_binding(name: str):
    path = PACK_ROOT / "functions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve


def write_fixture(workspace: Path) -> tuple[Path, Path]:
    samplesheet = workspace / "upstream_samplesheet.csv"
    samples: list[str] = []
    for group, subjects in (("Stim", (13, 15, 17, 19)), ("Kontroll", (14, 16, 18, 20))):
        for subject in subjects:
            for time in ("0h", "96h"):
                samples.append(f"{group}_{time}_{subject}")
    with samplesheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample", "fastq_1", "fastq_2"])
        for sample in samples:
            writer.writerow([sample, f"/fastq/{sample}.fastq.gz", ""])

    counts = workspace / "mature_counts.csv"
    rng = random.Random(7)
    features = [f"ssc-m-{idx}" for idx in range(1, 41)]
    with counts.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["", *features])
        for sample in samples:
            writer.writerow([sample, *[rng.randint(0, 2000) for _ in features]])
    return samplesheet, counts


def run_configurator(workspace: Path, samplesheet: Path, counts: Path, mode: str, check: bool = True):
    return subprocess.run(
        [
            sys.executable,
            str(workspace / "configure_analysis.py"),
            "--samplesheet",
            str(samplesheet),
            "--counts-file",
            str(counts),
            "--config",
            str(workspace / "config" / "analysis.yaml"),
            "--samples-out",
            str(workspace / "config" / "samples.csv"),
            mode,
        ],
        text=True,
        capture_output=True,
        check=check,
    )


def test_bindings(tmp: Path, samplesheet: Path, counts: Path) -> None:
    upstream = tmp / "nfcore_smrnaseq"
    edger = upstream / "results" / "mirna_quant" / "edger_qc"
    edger.mkdir(parents=True)
    shutil.copy2(counts, edger / "mature_counts.csv")
    shutil.copy2(counts, edger / "hairpin_counts.csv")
    rendered = upstream / "samplesheet.csv"
    shutil.copy2(samplesheet, rendered)
    entries = [
        {
            "id": "nfcore_smrnaseq",
            "path": "nfcore_smrnaseq",
            "params": {"samplesheet": "./samplesheet.csv", "genome": "Sscrofa11.1"},
            "outputs": {"rendered_samplesheet": str(rendered), "edger_qc_dir": str(edger)},
        }
    ]
    ctx = FakeContext(tmp, entries)
    assert load_binding("get_mirna_mature_counts")(ctx) == str((edger / "mature_counts.csv").resolve())
    assert load_binding("get_mirna_hairpin_counts")(ctx) == str((edger / "hairpin_counts.csv").resolve())
    assert load_binding("get_mirna_samplesheet")(ctx) == str(rendered.resolve())
    assert load_binding("get_mirna_organism")(ctx) == "sscrofa"


def test_configuration(workspace: Path, samplesheet: Path, counts: Path) -> None:
    generated = run_configurator(workspace, samplesheet, counts, "--auto-if-missing")
    assert "Wrote" in generated.stdout
    validated = run_configurator(workspace, samplesheet, counts, "--validate")
    assert "Validation passed" in validated.stdout
    config = yaml.safe_load((workspace / "config" / "analysis.yaml").read_text(encoding="utf-8"))
    assert config["reference_levels"] == {"group": "Kontroll", "time": "0h"}
    assert config["analysis"]["primary_contrast"] == "group_time_interaction"
    assert config["analysis"]["min_samples"] == 4
    assert [item["type"] for item in config["contrasts"]] == ["interaction", "two_group", "paired_time", "paired_time"]
    with (workspace / "config" / "samples.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 16
    assert {row["subject"] for row in rows} == {"13", "14", "15", "16", "17", "18", "19", "20"}

    config["analysis"]["primary_contrast"] = "missing_contrast"
    (workspace / "config" / "analysis.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    failed = run_configurator(workspace, samplesheet, counts, "--validate", check=False)
    assert failed.returncode == 2
    assert "primary_contrast" in failed.stdout
    config["analysis"]["primary_contrast"] = "group_time_interaction"
    (workspace / "config" / "analysis.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )

    rows.pop()
    with (workspace / "config" / "samples.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample", "include", "group", "time", "subject"])
        writer.writeheader()
        writer.writerows(rows)
    failed = run_configurator(workspace, samplesheet, counts, "--validate", check=False)
    assert failed.returncode == 2
    assert "complete" in failed.stdout.lower()


def test_build_inputs(workspace: Path, samplesheet: Path, counts: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(workspace / "build_mirna_inputs.py"),
            "--workspace-dir",
            str(workspace),
            "--results-dir",
            str(workspace / "results"),
            "--counts-file",
            str(counts),
            "--samplesheet",
            str(samplesheet),
            "--organism",
            "sscrofa",
            "--name",
            "Pig OIM",
            "--authors",
            "A, B",
        ],
        check=True,
    )
    inputs = (workspace / "mirna_inputs.R").read_text(encoding="utf-8")
    assert 'organism <- "sscrofa"' in inputs
    assert str(counts.resolve()) in inputs
    run_info = yaml.safe_load((workspace / "results" / "run_info.yaml").read_text(encoding="utf-8"))
    assert run_info["template"] == "mirna_differential"
    assert run_info["params"]["name"] == "Pig OIM"


def test_static_contract() -> None:
    manifest = yaml.safe_load((TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8"))
    assert manifest["id"] == "mirna_differential"
    assert manifest["run"] == {"mode": "render", "entry": "run.sh"}
    assert manifest["outputs"]["run_info"]["path"] == "run_info.yaml"
    assert manifest["outputs"]["runtime_command"]["path"] == "runtime_command.json"
    assert manifest["outputs"]["report_html"]["path"] == "../reports/miRNA_differential_report.html"
    assert manifest["outputs"]["comparison_reports"]["glob"] == "../reports/comparisons/*.html"
    assert manifest["outputs"]["tables"]["glob"] == "tables/**/*"
    assert manifest["outputs"]["figures"]["glob"] == "figures/**/*"
    run_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    assert "--configure|--validate" in run_text
    assert "pixi run install-bioc-data" in run_text
    assert 'if [[ -z "${LINKAR_INSTANCE_ID:-}" ]]' in run_text
    assert 'linkar collect "${script_dir}" --project "${script_dir}/.."' in run_text
    assert 'linkar clean "${script_dir}" --yes' in run_text
    qmd = (TEMPLATE_DIR / "miRNA_differential_report.qmd").read_text(encoding="utf-8")
    required_headings = [
        "# Main conclusion",
        "# Four comparisons, four biological questions",
        "# How the comparisons fit together",
        "# What the secondary results show",
        "# Data quality and global structure",
        "# Biological interpretation and follow-up",
        "# Methods and reproducibility",
    ]
    assert all(heading in qmd for heading in required_headings)
    assert "comparisons/" in qmd
    assert "four diagnostic/result figures" not in qmd
    contrast_qmd = (TEMPLATE_DIR / "miRNA_contrast_report.qmd").read_text(encoding="utf-8")
    assert "## Biological question" in contrast_qmd
    assert "How to read the direction" in contrast_qmd
    assert "Important limitation" in contrast_qmd
    assert "Return to the overview report" in contrast_qmd
    constructor = (TEMPLATE_DIR / "miRNA_constructor.R").read_text(encoding="utf-8")
    assert "MIRNA_CONTRAST_ID" in constructor
    assert 'file.path("reports", "comparisons")' in constructor
    assert '"--no-clean"' in constructor
    assert 'file.path("reports", "results")' in constructor
    assert 'file.path("reports", "comparisons", "results")' in constructor
    functions = (TEMPLATE_DIR / "miRNA_functions.R").read_text(encoding="utf-8")
    assert "~ subject_nested + time + group_time_interaction" in functions
    assert "assert_full_rank" in functions
    assert "shrunken_log2FoldChange" in functions
    assert 'paste0(stem, ".pdf")' in functions
    assert 'paste0(stem, ".svg")' in functions


def main() -> int:
    test_static_contract()
    with tempfile.TemporaryDirectory(prefix="linkar-mirna-differential-test-") as tmpdir:
        tmp = Path(tmpdir)
        workspace = tmp / "mirna_differential"
        shutil.copytree(
            TEMPLATE_DIR,
            workspace,
            ignore=shutil.ignore_patterns(".pixi", "__pycache__", "results", "reports"),
        )
        samplesheet, counts = write_fixture(workspace)
        test_build_inputs(workspace, samplesheet, counts)
        test_configuration(workspace, samplesheet, counts)
        test_bindings(tmp, samplesheet, counts)
    print("mirna_differential template tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
