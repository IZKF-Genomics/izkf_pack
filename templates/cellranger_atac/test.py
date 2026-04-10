#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import stat
import subprocess
import tempfile
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent


def make_fake_cellranger(bin_dir: Path) -> None:
    script = """#!/usr/bin/env python3
from __future__ import annotations
import csv
import sys
from pathlib import Path

args = sys.argv[1:]
if args == ["--version"]:
    print("cellranger-atac 2.2.0")
    raise SystemExit(0)
mode = args[0]
flags = {}
for arg in args[1:]:
    if not arg.startswith("--") or "=" not in arg:
        continue
    key, value = arg[2:].split("=", 1)
    flags[key] = value

if mode == "count":
    outdir = Path.cwd() / flags["id"] / "outs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "fragments.tsv.gz").write_text("fragments\\n", encoding="utf-8")
    (outdir / "singlecell.csv").write_text("barcode,is__cell_barcode\\n", encoding="utf-8")
    (outdir / "summary.csv").write_text("metric,value\\n", encoding="utf-8")
    (outdir / "web_summary.html").write_text("<html></html>\\n", encoding="utf-8")
elif mode == "aggr":
    csv_path = Path(flags["csv"])
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    if len(rows) < 2:
        raise SystemExit("expected at least two rows for aggr")
    outdir = Path.cwd() / flags["id"] / "outs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "summary.csv").write_text("metric,value\\n", encoding="utf-8")
    (outdir / "web_summary.html").write_text("<html></html>\\n", encoding="utf-8")
else:
    raise SystemExit(f"unsupported mode: {mode}")
"""
    path = bin_dir / "cellranger-atac"
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        fastq_dir = root / "fastqs"
        reference = root / "refdata-cellranger-atac-mm10-1.2.0"
        results_dir = root / "results"
        fake_bin = root / "bin"

        fastq_dir.mkdir()
        reference.mkdir()
        fake_bin.mkdir()
        make_fake_cellranger(fake_bin)

        for name in [
            "Ctrl_m_S1_L001_R1_001.fastq.gz",
            "Ctrl_m_S1_L001_R2_001.fastq.gz",
            "KO_f_S2_L001_R1_001.fastq.gz",
            "KO_f_S2_L001_R2_001.fastq.gz",
        ]:
            (fastq_dir / name).write_text("fq\n", encoding="utf-8")

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        completed = subprocess.run(
            [
                "python3",
                str(TEMPLATE_DIR / "run.py"),
                "--results-dir",
                str(results_dir),
                "--fastq-dir",
                str(fastq_dir),
                "--reference",
                str(reference),
                "--cellranger-atac-bin",
                str(fake_bin / "cellranger-atac"),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        assert "Discovered samples: Ctrl_m, KO_f" in completed.stdout
        assert (results_dir / "counts" / "Ctrl_m" / "outs" / "fragments.tsv.gz").exists()
        assert (results_dir / "counts" / "KO_f" / "outs" / "singlecell.csv").exists()
        assert (results_dir / "combined" / "outs" / "summary.csv").exists()
        assert (results_dir / "software_versions.json").exists()

        with (results_dir / "aggregation.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert [row["library_id"] for row in rows] == ["Ctrl_m", "KO_f"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
