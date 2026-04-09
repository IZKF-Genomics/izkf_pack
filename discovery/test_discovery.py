from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discovery.fastq_runs import list_fastq_runs
from discovery.projects import find_projects, get_project_summary, list_projects
from discovery.raw_runs import list_raw_runs
from discovery.references import list_references, recommended_references


class DiscoveryTests(unittest.TestCase):
    def test_project_discovery_reads_project_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "projects"
            project_dir = root / "demo_project"
            project_dir.mkdir(parents=True)
            (project_dir / "project.yaml").write_text(
                "id: demo\nactive_pack: izkf\npacks: []\ntemplates:\n  - id: demultiplex\n  - id: cellranger_atac\n",
                encoding="utf-8",
            )

            projects = list_projects(root)
            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0]["id"], "demo")
            self.assertEqual(projects[0]["linkar_runs"], 2)
            self.assertEqual(projects[0]["recent_templates"], ["demultiplex", "cellranger_atac"])

            summary = get_project_summary(project_dir)
            self.assertTrue(summary["has_project_yaml"])

            matches = find_projects("demo", root)
            self.assertEqual(len(matches), 1)

    def test_fastq_discovery_counts_fastqs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fastq"
            run_dir = root / "240101_RUN"
            run_dir.mkdir(parents=True)
            (run_dir / "sample_R1_001.fastq.gz").write_text("fq\n", encoding="utf-8")
            (run_dir / "sample_R2_001.fastq.gz").write_text("fq\n", encoding="utf-8")

            runs = list_fastq_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["fastq_file_count"], 2)

    def test_raw_discovery_handles_nested_instrument_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "raw"
            run_dir = root / "A01742" / "240101_A01742_0001_ABC123"
            run_dir.mkdir(parents=True)
            (run_dir / "SampleSheet.csv").write_text("sample sheet\n", encoding="utf-8")

            runs = list_raw_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["instrument"], "A01742")
            self.assertTrue(runs[0]["has_samplesheet"])

    def test_reference_discovery_and_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "refs"
            (root / "refdata-cellranger-arc-GRCm39-2024-A").mkdir(parents=True)
            (root / "refdata-cellranger-arc-GRCh38-2024-A").mkdir(parents=True)

            refs = list_references(root)
            self.assertEqual(len(refs), 2)

            ranked = recommended_references(organism="GRCm39", workflow="arc", roots=root)
            self.assertEqual(ranked[0]["name"], "refdata-cellranger-arc-GRCm39-2024-A")


if __name__ == "__main__":
    unittest.main()
