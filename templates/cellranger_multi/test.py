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

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
PACK_ROOT = TEMPLATE_DIR.parent.parent


def load_binding(name: str):
    path = PACK_ROOT / "functions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve


def make_fake_cellranger(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import csv
import sys
from pathlib import Path
if sys.argv[1:] == ["--version"]:
    print("cellranger 10.0.0")
    raise SystemExit(0)
if sys.argv[1] != "multi":
    raise SystemExit("expected multi")
flags = dict(arg[2:].split("=", 1) for arg in sys.argv[2:] if arg.startswith("--") and "=" in arg)
out = Path.cwd() / flags["id"] / "outs"
out.mkdir(parents=True)
(out / "qc_report.html").write_text("<html></html>\\n")
(out / "qc_library_metrics.csv").write_text("metric,value\\nreads,1\\n")
(out / "qc_sample_metrics.csv").write_text("metric,value\\ncells,1\\n")
(out / "filtered_feature_bc_matrix.h5").write_text("matrix\\n")
(out / "raw_feature_bc_matrix.h5").write_text("matrix\\n")
(out / "raw_molecule_info.h5").write_text("molecules\\n")
mux = out / "multiplexing_analysis"
mux.mkdir()
(mux / "tag_calls_summary.csv").write_text("Category,num_cells\\n1 tag assigned,3\\n")
sample_ids = []
section = ""
with Path(flags["csv"]).open(newline="") as handle:
    for row in csv.reader(handle):
        if len(row) == 1 and row[0].startswith("["):
            section = row[0]
        elif section == "[samples]" and row and row[0] != "sample_id":
            sample_ids.append(row[0])
for sample_id in sample_ids:
    sample_out = out / "per_sample_outs" / sample_id
    sample_out.mkdir(parents=True)
    (sample_out / "web_summary.html").write_text("<html></html>\\n")
    (sample_out / "metrics_summary.csv").write_text("metric,value\\ncells,1\\n")
    (sample_out / "sample_filtered_feature_bc_matrix.h5").write_text("matrix\\n")
    (sample_out / "sample_molecule_info.h5").write_text("molecules\\n")
    (sample_out / "sample_cloupe.cloupe").write_text("cloupe\\n")
    (sample_out / "sample_alignments.bam").write_text("bam\\n")
    (sample_out / "sample_alignments.bam.bai").write_text("index\\n")
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_samples(path: Path, fastq_dir: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sample", "gex_fastq_id", "gex_fastqs", "feature_fastq_id", "feature_fastqs", "feature_types"],
        )
        writer.writeheader()
        for sample in ("WT_ctrl", "WT_LPS", "TLR4_ctrl", "TLR4_LPS"):
            writer.writerow(
                {
                    "sample": sample,
                    "gex_fastq_id": f"{sample}_GEX",
                    "gex_fastqs": fastq_dir,
                    "feature_fastq_id": f"{sample}_FB",
                    "feature_fastqs": fastq_dir,
                    "feature_types": "Antibody Capture",
                }
            )


def test_render_and_execute() -> None:
    with tempfile.TemporaryDirectory(prefix="cellranger-multi-test-") as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        shutil.copytree(TEMPLATE_DIR, workspace)
        fastq_dir = root / "fastqs"
        reference = root / "reference"
        bin_dir = root / "bin"
        fastq_dir.mkdir()
        reference.mkdir()
        bin_dir.mkdir()
        samples = root / "samples.csv"
        write_samples(samples, fastq_dir)
        fake_cellranger = bin_dir / "cellranger"
        make_fake_cellranger(fake_cellranger)

        rendered = subprocess.run(
            [
                "python3",
                str(workspace / "run.py"),
                "render",
                "--samplesheet",
                str(samples),
                "--genome",
                "GRCm39",
                "--reference",
                str(reference),
                "--cellranger-bin",
                str(fake_cellranger),
                "--localcores",
                "8",
                "--localmem",
                "32",
            ],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        assert rendered.returncode == 0, rendered.stderr
        settings = workspace / "config" / "cellranger_multi.toml"
        settings.write_text(
            settings.read_text(encoding="utf-8")
            .replace('source = "__EDIT_ME__"', 'source = "file"'),
            encoding="utf-8",
        )
        (workspace / "config" / "custom_feature_reference.csv").write_text(
            "id,name,read,pattern,sequence,feature_type\n"
            "Hashtag1,Hashtag1_TotalSeqC,R2,5PNNNNNNNNNN(BC),ACCCACCAGTAAGAC,Antibody Capture\n"
            "Hashtag2,Hashtag2_TotalSeqC,R2,5PNNNNNNNNNN(BC),GGTCGAGAGCATTCA,Antibody Capture\n"
            "Hashtag3,Hashtag3_TotalSeqC,R2,5PNNNNNNNNNN(BC),CTTGCCGCATGTCAT,Antibody Capture\n",
            encoding="utf-8",
        )
        with (workspace / "config" / "sample_assignments.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["gem_well", "sample_id", "hashtag_ids"])
            writer.writeheader()
            for gem_well in ("WT_ctrl", "WT_LPS", "TLR4_ctrl", "TLR4_LPS"):
                for replicate in range(1, 4):
                    writer.writerow(
                        {
                            "gem_well": gem_well,
                            "sample_id": f"{gem_well}_rep{replicate}",
                            "hashtag_ids": f"Hashtag{replicate}",
                        }
                    )
        results = workspace / "results"
        executed = subprocess.run(
            ["python3", str(workspace / "run.py"), "execute", "--workspace", str(workspace), "--results-dir", str(results)],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        assert executed.returncode == 0, executed.stderr
        assert len(list((workspace / "generated" / "multi").glob("*.csv"))) == 4
        assert (workspace / "generated" / "feature_reference.csv").exists()
        config_text = (workspace / "generated" / "multi" / "TLR4_LPS.csv").read_text(encoding="utf-8")
        assert "[samples]" in config_text
        assert "TLR4_LPS_rep1,Hashtag1" in config_text
        for sample in ("WT_ctrl", "WT_LPS", "TLR4_ctrl", "TLR4_LPS"):
            assert (results / sample / "outs" / "qc_report.html").exists()
        payload = json.loads((results / "runtime_command.json").read_text(encoding="utf-8"))
        assert len(payload["commands"]) == 4
        assert payload["feature_reference"].startswith("file:")

        declared = yaml.safe_load((workspace / "linkar_template.yaml").read_text(encoding="utf-8"))["outputs"]
        collected = {}
        for name, output_spec in declared.items():
            if "path" in output_spec:
                candidate = (results / output_spec["path"]).resolve()
                if candidate.exists():
                    collected[name] = candidate
            elif "glob" in output_spec:
                matches = sorted(results.glob(output_spec["glob"]))
                if matches:
                    collected[name] = matches
            elif name == "results_dir":
                collected[name] = results
        for required in (
            "results_dir",
            "sample_manifest",
            "settings",
            "sample_assignments",
            "generated_multi_configs",
            "cellranger_outs_dirs",
            "qc_reports",
            "per_sample_web_summaries",
            "qc_library_metrics",
            "qc_sample_metrics",
            "per_sample_metrics",
            "multiplexing_analysis",
            "per_sample_filtered_matrices",
            "per_sample_molecule_info",
            "per_sample_cloupe_files",
            "per_sample_bams",
            "per_sample_bam_indexes",
            "runtime_command",
            "software_versions",
        ):
            assert required in collected, f"Linkar output was not collectable: {required}"


def test_binding_pairs_gex_and_fb() -> None:
    with tempfile.TemporaryDirectory(prefix="cellranger-multi-binding-") as tmp:
        root = Path(tmp)
        fastqs = root / "fastqs"
        fastqs.mkdir()
        paths = []
        for library in ("WT_ctrl_GEX", "WT_ctrl_FB", "WT_LPS_GEX", "WT_LPS_FB"):
            for read in (1, 2):
                path = fastqs / f"{library}_S1_R{read}_001.fastq.gz"
                path.write_text("fq\n", encoding="utf-8")
                paths.append(str(path))
        phix = fastqs / "PhiX_S1_R1_001.fastq.gz"
        phix.write_text("fq\n", encoding="utf-8")
        paths.append(str(phix))

        class Project:
            data = {"templates": [{"id": "demultiplex", "outputs": {"demux_fastq_files": paths}}]}

        class Context:
            project = Project()

            def latest_output(self, key, template_id=None):
                return None

        previous_linkar_home = os.environ.get("LINKAR_HOME")
        os.environ["LINKAR_HOME"] = str(root / "linkar-home")
        try:
            output = Path(load_binding("generate_cellranger_multi_samplesheet")(Context()))
        finally:
            if previous_linkar_home is None:
                os.environ.pop("LINKAR_HOME", None)
            else:
                os.environ["LINKAR_HOME"] = previous_linkar_home
        rows = list(csv.DictReader(output.open(encoding="utf-8")))
        assert [row["sample"] for row in rows] == ["WT_LPS", "WT_ctrl"]
        assert all(row["feature_types"] == "Antibody Capture" for row in rows)


def test_pack_registration() -> None:
    data = yaml.safe_load((PACK_ROOT / "linkar_pack.yaml").read_text(encoding="utf-8"))
    params = data["templates"]["cellranger_multi"]["params"]
    assert params["samplesheet"]["function"] == "generate_cellranger_multi_samplesheet"
    assert params["genome"]["function"] == "get_cellranger_multi_genome"


def test_collection_uses_active_project() -> None:
    run_script = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    assert 'collect_args+=(--project "${LINKAR_PROJECT_DIR}")' in run_script


def test_checked_in_catalog() -> None:
    spec = importlib.util.spec_from_file_location("cellranger_multi_run", TEMPLATE_DIR / "run.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest_path = TEMPLATE_DIR / "catalogs" / "manifest.tsv"
    manifest = list(csv.DictReader(manifest_path.open(encoding="utf-8"), delimiter="\t"))
    assert len(manifest) == 12
    for entry in manifest:
        path = TEMPLATE_DIR / "catalogs" / entry["file"]
        _, rows = module.load_feature_rows(path, delimiter="\t")
        module.validate_feature_rows(rows, path)
        assert rows
        assert len(rows) == int(entry["row_count"])
        assert {row["feature_type"] for row in rows} == {"Antibody Capture"}


def main() -> None:
    test_render_and_execute()
    test_binding_pairs_gex_and_fb()
    test_pack_registration()
    test_collection_uses_active_project()
    test_checked_in_catalog()
    print("cellranger_multi template test passed")


if __name__ == "__main__":
    main()
