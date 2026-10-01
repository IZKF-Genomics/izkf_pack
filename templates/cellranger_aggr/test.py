#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
PACK_ROOT = TEMPLATE_DIR.parent.parent


def load_binding():
    path = PACK_ROOT / "functions" / "generate_cellranger_aggr_csv.py"
    spec = importlib.util.spec_from_file_location("test_generate_cellranger_aggr_csv", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_fake_cellranger(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import csv
import json
import sys
from pathlib import Path

if sys.argv[1:] == ["--version"]:
    print("cellranger 10.0.0")
    raise SystemExit(0)
if len(sys.argv) < 2 or sys.argv[1] != "aggr":
    raise SystemExit("expected cellranger aggr")
flags = dict(arg[2:].split("=", 1) for arg in sys.argv[2:] if arg.startswith("--") and "=" in arg)
rows = list(csv.DictReader(Path(flags["csv"]).open(encoding="utf-8")))
if len(rows) < 2:
    raise SystemExit("expected at least two aggregation rows")
out = Path.cwd() / flags["id"] / "outs"
count = out / "count"
analysis = count / "analysis"
analysis.mkdir(parents=True)
(out / "web_summary.html").write_text("<html></html>\\n", encoding="utf-8")
(out / "aggregation.csv").write_text(Path(flags["csv"]).read_text(encoding="utf-8"), encoding="utf-8")
(count / "summary.json").write_text(json.dumps({"lowest_frac_reads_kept": 1.0}), encoding="utf-8")
(count / "filtered_feature_bc_matrix.h5").write_text("matrix\\n", encoding="utf-8")
(count / "cloupe.cloupe").write_text("cloupe\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_molecules(root: Path, sample_ids: list[str]) -> list[Path]:
    paths = []
    for sample_id in sample_ids:
        path = root / sample_id / "outs" / "per_sample_outs" / sample_id / "sample_molecule_info.h5"
        path.parent.mkdir(parents=True)
        path.write_text("molecules\n", encoding="utf-8")
        paths.append(path)
    return paths


def test_binding(root: Path) -> None:
    module = load_binding()
    molecules = make_molecules(root / "upstream", ["condition_a_rep1", "condition_a_rep2"])
    ctx = SimpleNamespace(
        project=SimpleNamespace(
            data={
                "templates": [
                    {
                        "id": "cellranger_multi",
                        "outputs": {"per_sample_molecule_info": [str(path) for path in molecules]},
                    }
                ]
            }
        )
    )
    old_home = os.environ.get("LINKAR_HOME")
    os.environ["LINKAR_HOME"] = str(root / "linkar-home")
    try:
        generated = Path(module.resolve(ctx))
    finally:
        if old_home is None:
            os.environ.pop("LINKAR_HOME", None)
        else:
            os.environ["LINKAR_HOME"] = old_home
    with generated.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == ["sample_id", "molecule_h5"]
    assert [row["sample_id"] for row in rows] == ["condition_a_rep1", "condition_a_rep2"]
    assert all(Path(row["molecule_h5"]).is_absolute() for row in rows)


def test_binding_full_multi_and_vdj(root: Path) -> None:
    module = load_binding()
    old_home = os.environ.get("LINKAR_HOME")
    os.environ["LINKAR_HOME"] = str(root / "linkar-home-variants")
    try:
        molecule_paths = make_molecules(root / "multi-upstream", ["sample_a", "sample_b"])
        for molecule in molecule_paths:
            vdj = molecule.parent / "vdj_b"
            vdj.mkdir()
            (vdj / "vdj_contig_info.pb").write_text("contigs\n", encoding="utf-8")
        multi_ctx = SimpleNamespace(
            project=SimpleNamespace(
                data={
                    "templates": [
                        {
                            "id": "cellranger_multi",
                            "outputs": {"per_sample_molecule_info": [str(path) for path in molecule_paths]},
                        }
                    ]
                }
            )
        )
        multi_csv = Path(module.resolve(multi_ctx))
        with multi_csv.open(encoding="utf-8", newline="") as handle:
            multi_rows = list(csv.DictReader(handle))
        assert list(multi_rows[0]) == ["sample_id", "sample_outs", "donor", "origin"]
        assert all(row["donor"] == "__EDIT_ME__" for row in multi_rows)

        vdj_paths = []
        for sample in ("donor_a", "donor_b"):
            path = root / "vdj-upstream" / sample / "outs" / "vdj_contig_info.pb"
            path.parent.mkdir(parents=True)
            path.write_text("contigs\n", encoding="utf-8")
            vdj_paths.append(path)
        vdj_ctx = SimpleNamespace(
            project=SimpleNamespace(
                data={
                    "templates": [
                        {
                            "id": "cellranger_vdj",
                            "outputs": {"vdj_contig_info": [str(path) for path in vdj_paths]},
                        }
                    ]
                }
            )
        )
        vdj_csv = Path(module.resolve(vdj_ctx))
        with vdj_csv.open(encoding="utf-8", newline="") as handle:
            vdj_rows = list(csv.DictReader(handle))
        assert list(vdj_rows[0]) == ["sample_id", "vdj_contig_info", "donor", "origin"]
        assert [row["sample_id"] for row in vdj_rows] == ["donor_a", "donor_b"]

        legacy_paths = []
        for sample in ("legacy_a", "legacy_b"):
            path = root / "legacy-multi" / "outs" / "per_sample_outs" / sample / "count" / "sample_molecule_info.h5"
            path.parent.mkdir(parents=True)
            path.write_text("molecules\n", encoding="utf-8")
            legacy_paths.append(path)
        legacy_ctx = SimpleNamespace(
            project=SimpleNamespace(
                data={
                    "templates": [
                        {
                            "id": "cellranger_multi",
                            "outputs": {"per_sample_molecule_info": [str(path) for path in legacy_paths]},
                        }
                    ]
                }
            )
        )
        legacy_csv = Path(module.resolve(legacy_ctx))
        with legacy_csv.open(encoding="utf-8", newline="") as handle:
            legacy_rows = list(csv.DictReader(handle))
        assert [row["sample_id"] for row in legacy_rows] == ["legacy_a", "legacy_b"]
    finally:
        if old_home is None:
            os.environ.pop("LINKAR_HOME", None)
        else:
            os.environ["LINKAR_HOME"] = old_home


def test_render_execute(root: Path) -> None:
    workspace = root / "workspace"
    shutil.copytree(TEMPLATE_DIR, workspace)
    fake_cellranger = root / "bin" / "cellranger"
    fake_cellranger.parent.mkdir()
    make_fake_cellranger(fake_cellranger)
    molecules = make_molecules(root / "inputs", ["sample_1", "sample_2"])
    source_csv = root / "aggregation.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "molecule_h5", "condition"])
        writer.writeheader()
        writer.writerow({"sample_id": "sample_1", "molecule_h5": molecules[0], "condition": "control"})
        writer.writerow({"sample_id": "sample_2", "molecule_h5": molecules[1], "condition": "treated"})

    rendered = subprocess.run(
        [
            "python3",
            str(workspace / "run.py"),
            "render",
            "--aggregation-csv",
            str(source_csv),
            "--cellranger-bin",
            str(fake_cellranger),
            "--localcores",
            "8",
            "--localmem",
            "64",
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rendered.returncode == 0, rendered.stderr
    assert "detected mode: Gene Expression / Feature Barcode" in rendered.stdout

    prepared = subprocess.run(
        [str(workspace / "run.sh"), "--prepare-only"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    assert prepared.returncode == 0, prepared.stderr
    assert "[ready] preflight succeeded" in prepared.stdout
    runtime = json.loads((workspace / "results" / "runtime_command.json").read_text(encoding="utf-8"))
    assert runtime["input_count"] == 2
    assert runtime["input_mode"] == "molecule_h5"
    assert runtime["normalization"] == "none"

    executed = subprocess.run(
        [str(workspace / "run.sh")],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    assert executed.returncode == 0, executed.stderr
    assert "[done] Cell Ranger aggr completed" in executed.stdout
    assert (workspace / "results" / "aggregated" / "outs" / "web_summary.html").exists()
    assert (workspace / "results" / "aggregated" / "outs" / "count" / "summary.json").exists()


def test_placeholders_are_blocked(root: Path) -> None:
    workspace = root / "placeholder-workspace"
    shutil.copytree(TEMPLATE_DIR, workspace)
    fake_cellranger = root / "placeholder-bin" / "cellranger"
    fake_cellranger.parent.mkdir()
    make_fake_cellranger(fake_cellranger)
    sample_outs = []
    for sample in ("sample_a", "sample_b"):
        path = root / "multi" / sample
        path.mkdir(parents=True)
        (path / "sample_molecule_info.h5").write_text("molecules\n", encoding="utf-8")
        sample_outs.append(path)
    source_csv = root / "multi.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "sample_outs", "donor", "origin"])
        writer.writeheader()
        for sample, path in zip(("sample_a", "sample_b"), sample_outs):
            writer.writerow(
                {"sample_id": sample, "sample_outs": path, "donor": "__EDIT_ME__", "origin": "blood"}
            )
    rendered = subprocess.run(
        [
            "python3",
            str(workspace / "run.py"),
            "render",
            "--aggregation-csv",
            str(source_csv),
            "--cellranger-bin",
            str(fake_cellranger),
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rendered.returncode == 0, rendered.stderr
    blocked = subprocess.run(
        [str(workspace / "run.sh"), "--prepare-only"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    assert blocked.returncode != 0
    assert "donor still contains a placeholder" in blocked.stderr


def test_manifest() -> None:
    manifest = yaml.safe_load((TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8"))
    assert manifest["id"] == "cellranger_aggr"
    assert manifest["run"]["mode"] == "render"
    outputs = manifest["outputs"]
    for name in (
        "web_summaries",
        "summary_json",
        "filtered_feature_matrices_h5",
        "cloupe_files",
        "vloupe_files",
        "runtime_command",
        "software_versions",
    ):
        assert name in outputs
    run_script = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    assert 'collect_args+=(--project "${LINKAR_PROJECT_DIR}")' in run_script


def main() -> int:
    test_manifest()
    with tempfile.TemporaryDirectory(prefix="cellranger-aggr-test-") as tmp:
        root = Path(tmp)
        test_binding(root)
        test_binding_full_multi_and_vdj(root)
        test_render_execute(root)
        test_placeholders_are_blocked(root)
    print("cellranger_aggr tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
