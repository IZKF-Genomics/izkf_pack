#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent


def load_run_module():
    path = TEMPLATE_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("methods_run", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generation_with_runtime_command() -> None:
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
                    "command": ["bash", "run.sh"],
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
                        {"name": "cellranger-atac", "version": "cellranger-atac 2.2.0", "source": "command"},
                        {"name": "reference", "version": "refdata-cellranger-arc-GRCh38-2024-A", "source": "param"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        (results_source / "runtime_command.json").write_text(
            json.dumps(
                {
                    "template": "cellranger_atac",
                    "engine": "binary",
                    "pipeline": "cellranger-atac",
                    "pipeline_version": "2.2.0",
                    "command": ["cellranger-atac", "count", "--id", "sample_a"],
                    "command_pretty": "cellranger-atac count --id sample_a --reference /refs/example_reference",
                    "params": {"reference": "/refs/example_reference", "run_aggr": True, "localcores": 8},
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
                                "runtime_command": str(results_source / "runtime_command.json"),
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
        prompt = (results_dir / "methods_prompt.md").read_text(encoding="utf-8")
        response = json.loads((results_dir / "methods_response.json").read_text(encoding="utf-8"))

        assert "Single-cell ATAC-seq processing" in long_text
        assert "example_reference" in long_text
        assert "Cell Ranger ATAC" in long_text
        assert "2.2.0" in long_text
        assert "### Computational Approach" not in long_text
        assert "### Relevant Settings" in long_text
        assert "### Software" in long_text
        assert "### References" in long_text
        assert "cellranger-atac count --id sample_a" not in long_text
        assert "Linkar" not in long_text
        assert "recorded project author" not in long_text.lower()
        assert "Project-level sequencing metadata were recovered" not in long_text
        assert "publication-relevant workflow step" not in short_text
        assert "References" in short_text
        assert short_text.strip().splitlines()[0].endswith(".")
        assert "\n\n" in short_text
        assert "\n1. " in short_text
        assert "Cell Ranger ATAC" in refs
        assert "runtime_command" in prompt
        assert context["runs"][0]["template"] == "cellranger_atac"
        assert context["runs"][0]["runtime_command"]["pipeline"] == "cellranger-atac"
        assert context["runs"][0]["runtime_command"]["command_pretty"].startswith("cellranger-atac count")
        assert context["runs"][0]["catalog"]["method_core"]
        assert context["runs"][0]["interpreted_params"][0]["name"] == "reference"
        assert response["used_llm"] is False


def test_dgea_label_and_software_version_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        project_dir = root / "project"
        results_dir = root / "results"
        run_dir = project_dir / "DGEA_Liver"
        (run_dir / ".linkar").mkdir(parents=True)
        (run_dir / ".linkar" / "runtime.json").write_text(
            json.dumps({"success": True, "returncode": 0}),
            encoding="utf-8",
        )
        results_source = run_dir / "results"
        results_source.mkdir()
        (results_source / "software_versions.json").write_text(
            json.dumps({"software": [{"name": "quarto", "version": "1.6.0", "source": "command"}]}),
            encoding="utf-8",
        )
        project_dir.mkdir(exist_ok=True)
        (project_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "example_project_002",
                    "author": {"name": "Example User", "organization": "Example Org"},
                    "templates": [
                        {
                            "id": "dgea",
                            "template_version": "0.1.2",
                            "instance_id": "dgea_001",
                            "path": "DGEA_Liver",
                            "params": {
                                "samplesheet": "/tmp/samplesheet.csv",
                                "organism": "sscrofa",
                                "application": "3mrnaseq",
                                "name": "Liver",
                            },
                            "outputs": {},
                        }
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        subprocess.run(
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

        long_text = (results_dir / "methods_long.md").read_text(encoding="utf-8")
        context = yaml.safe_load((results_dir / "methods_context.yaml").read_text(encoding="utf-8"))
        assert "Differential gene expression analysis: Liver" in long_text
        assert "### Computational Approach" not in long_text
        assert "### Relevant Settings" in long_text
        assert "### Software" in long_text
        assert "### References" in long_text
        assert "Quarto" in long_text
        assert "Linkar" not in long_text
        assert context["runs"][0]["label"] == "Differential gene expression analysis: Liver"
        assert context["runs"][0]["software_versions"][0]["name"] == "quarto"
        assert context["runs"][0]["run_dir"].endswith("DGEA_Liver")


def test_ercc_catalog_entry_shapes_methods_text() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        project_dir = root / "project"
        results_dir = root / "results"
        run_dir = project_dir / "ercc"
        (run_dir / ".linkar").mkdir(parents=True)
        (run_dir / ".linkar" / "runtime.json").write_text(
            json.dumps({"success": True, "returncode": 0}),
            encoding="utf-8",
        )
        results_source = run_dir / "results"
        results_source.mkdir()
        (results_source / "software_versions.json").write_text(
            json.dumps(
                {
                    "software": [
                        {"name": "pixi", "version": "pixi 0.64.0", "source": "command"},
                        {"name": "quarto", "version": "1.6.0", "source": "command"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        project_dir.mkdir(exist_ok=True)
        (project_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "example_project_003",
                    "author": {"name": "Example User", "organization": "Example Org"},
                    "templates": [
                        {
                            "id": "ercc",
                            "template_version": "0.1.0",
                            "instance_id": "ercc_001",
                            "path": "ercc",
                            "params": {
                                "salmon_dir": "/tmp/star_salmon",
                                "samplesheet": "/tmp/samplesheet.csv",
                                "authors": "Example User",
                            },
                            "outputs": {
                                "results_dir": str(results_source),
                            },
                        }
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        subprocess.run(
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

        long_text = (results_dir / "methods_long.md").read_text(encoding="utf-8")
        refs = (results_dir / "methods_references.md").read_text(encoding="utf-8")
        context = yaml.safe_load((results_dir / "methods_context.yaml").read_text(encoding="utf-8"))
        assert "ERCC spike-in quality control" in long_text
        assert "Salmon quantification results" in long_text
        assert "### Computational Approach" not in long_text
        assert "### References" in long_text
        assert "Example User" not in long_text
        assert "Linkar" not in long_text
        assert "Synthetic spike-in standards for RNA-seq experiments" in refs
        assert context["runs"][0]["label"] == "ERCC spike-in quality control"
        assert context["runs"][0]["catalog"]["method_core"]


def test_run_sh_resolves_project_dir_from_linkar_runtime_copy() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        project_dir = root / "project"
        results_dir = root / "results"
        runtime_dir = project_dir / ".linkar" / "runs" / "methods_001"
        runtime_dir.mkdir(parents=True)
        project_dir.mkdir(exist_ok=True)

        (project_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "example_project_004",
                    "author": {"name": "Example User", "organization": "Example Org"},
                    "templates": [],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        shutil.copy2(TEMPLATE_DIR / "run.py", runtime_dir / "run.py")
        shutil.copy2(TEMPLATE_DIR / "run.sh", runtime_dir / "run.sh")
        shutil.copy2(TEMPLATE_DIR / "methods_catalog.yaml", runtime_dir / "methods_catalog.yaml")
        (runtime_dir / "run.sh").chmod(0o755)

        env = os.environ.copy()
        env["LINKAR_RESULTS_DIR"] = str(results_dir)
        env["PROJECT_DIR"] = str(root)
        completed = subprocess.run(
            [str(runtime_dir / "run.sh")],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=root,
        )

        assert "methods_context.yaml" in completed.stdout
        context = yaml.safe_load((results_dir / "methods_context.yaml").read_text(encoding="utf-8"))
        assert context["project"]["path"] == str(project_dir.resolve())


def test_llm_config_resolution() -> None:
    module = load_run_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        config_path = project_dir / ".methods_llm.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "base_url": "https://api.example.org/v1",
                    "model": "gpt-5.4-mini",
                    "temperature": 0.3,
                    "api_key_env": "ALT_OPENAI_KEY",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        args = argparse.Namespace(
            results_dir="unused",
            project_dir=str(project_dir),
            style="publication",
            use_llm="true",
            llm_config=str(project_dir),
            llm_base_url="",
            llm_model="",
            llm_temperature=0.2,
        )
        env_before = {
            "ALT_OPENAI_KEY": os.environ.get("ALT_OPENAI_KEY"),
            "LINKAR_LLM_API_KEY": os.environ.get("LINKAR_LLM_API_KEY"),
            "LINKAR_LLM_BASE_URL": os.environ.get("LINKAR_LLM_BASE_URL"),
            "LINKAR_LLM_MODEL": os.environ.get("LINKAR_LLM_MODEL"),
        }
        os.environ["ALT_OPENAI_KEY"] = "test-secret"
        os.environ.pop("LINKAR_LLM_API_KEY", None)
        os.environ["LINKAR_LLM_BASE_URL"] = "https://env.example.org/v1"
        os.environ["LINKAR_LLM_MODEL"] = "env-model"
        try:
            settings = module.resolve_llm_settings(args, project_dir)
        finally:
            for key, value in env_before.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        assert settings["config_path"] == str(config_path)
        assert settings["base_url"] == "https://env.example.org/v1"
        assert settings["model"] == "env-model"
        assert settings["api_key"] == "test-secret"
        assert settings["api_key_source"] == "ALT_OPENAI_KEY"


def test_project_api_metadata_resolution_and_rendering() -> None:
    module = load_run_module()
    sample_payload = [
        {
            "ProjectOutput": {
                "agendo_application": "3mRNAseq",
                "application": "3mRNAseq",
                "umi": "UMI Second Strand SynthesisModule for QuantSeq FWD",
                "spike_in": "ERCC RNA Spike-in Mix",
                "library_kit": "QuantSeq 3' mRNA-Seq Library Prep Kit v2 FWD for Illumina",
                "index_kit": "Lexogen UDI 12 nt Unique Dual Indexing Set A1 Cat.#198.96",
                "sequencer": "NextSeq",
                "sequencing_kit": "NextSeq 500/550 High Output v2.5 kit (75 cycles)",
                "read_type": "single-end",
                "cycles_read1": 76,
                "cycles_index1": 8,
                "cycles_index2": 8,
                "run_date": "2026-04-16T00:00:00",
                "flow_cell": "HWJHLBGYX",
                "agendo_id": 5437,
                "phix_percentage": 20,
                "sample_number": 32,
                "project": "Seq-00286",
            },
            "RunMetadataDB": {
                "instrument": "NB501289",
            },
            "PredictionConfidence": 1,
        }
    ]
    original = module.load_cached_combined_project_metadata
    module.load_cached_combined_project_metadata = lambda agendo_id, base_url: sample_payload
    try:
        metadata = module.resolve_project_api_metadata(
            {
                "templates": [
                    {
                        "id": "nfcore_3mrnaseq",
                        "params": {"agendo_id": "5437"},
                    }
                ]
            },
            "https://example.org/api",
        )
        context = {
            "project_api": metadata,
            "runs": [],
        }
        long_text = module.deterministic_long_methods(context, {"references": {}})
    finally:
        module.load_cached_combined_project_metadata = original

    assert metadata["fetched"] is True
    assert metadata["project_metadata"]["agendo_id"] == "5437"
    assert metadata["project_metadata"]["library_kit"].startswith("QuantSeq 3' mRNA-Seq")
    assert metadata["project_metadata"]["flow_cell"] == "HWJHLBGYX"
    assert metadata["project_metadata"]["sequencer"] == "NextSeq"
    assert "## Project Assay Metadata" in long_text
    assert "Library kit" in long_text
    assert "Read configuration" in long_text
    assert "single-end; R1 76/I1 8/I2 8" in long_text
    assert "libraries were prepared using" in long_text


def test_nfcore_reference_and_command_details_ignore_project_umi() -> None:
    module = load_run_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_path = root / "nextflow.config"
        config_path.write_text(
            """
params {
    genomes {
        'Sscrofa11.1' {
            fasta = '/data/ref_genomes/Sscrofa11.1/src/Sus_scrofa.Sscrofa11.1.dna.toplevel.fa'
            gtf   = '/data/ref_genomes/Sscrofa11.1/src/Sus_scrofa.Sscrofa11.1.115.gtf'
        }
        'Sscrofa11.1_with_ERCC' {
            fasta = '/data/ref_genomes/Sscrofa11.1_with_ERCC/src/Sscrofa11.1_with_ERCC.fa'
            gtf   = '/data/ref_genomes/Sscrofa11.1_with_ERCC/src/Sscrofa11.1_with_ERCC.gtf'
        }
    }
}
""".strip()
            + "\n",
            encoding="utf-8",
        )
        run = {
            "template": "nfcore_3mrnaseq",
            "params": {"genome": "Sscrofa11.1", "spikein": "ERCC RNA Spike-in Mix"},
            "runtime_command": {
                "pipeline_version": "3.22.2",
                "command": [
                    "pixi",
                    "run",
                    "nextflow",
                    "run",
                    "nf-core/rnaseq",
                    "-r",
                    "3.22.2",
                    "-profile",
                    "docker",
                    "--genome",
                    "Sscrofa11.1_with_ERCC",
                    "--gencode",
                    "--featurecounts_group_type",
                    "gene_type",
                    "--extra_salmon_quant_args=--noLengthCorrection",
                ],
                "command_pretty": "pixi run nextflow run nf-core/rnaseq -r 3.22.2 -profile docker --genome Sscrofa11.1_with_ERCC --gencode --featurecounts_group_type gene_type --extra_salmon_quant_args=--noLengthCorrection",
                "params": {
                    "effective_genome": "Sscrofa11.1_with_ERCC",
                    "genome": "Sscrofa11.1",
                    "spikein": "ERCC RNA Spike-in Mix",
                    "umi": "--spike-in",
                },
                "artifacts": {"nextflow_config": str(config_path)},
            },
        }
        context = {
            "project_api": {
                "project_metadata": {
                    "umi": "UMI Second Strand SynthesisModule for QuantSeq FWD",
                }
            }
        }

        settings = module.collect_setting_bullets(run, context)
        reference_details = module.collect_reference_detail_bullets(run)
        command_params = module.collect_command_parameter_bullets(run, context)
        command_block = module.collect_recorded_command_block(run)

    assert not any("UMI" in line for line in settings)
    assert any("Annotation version" in line and "115" in line for line in reference_details)
    assert any("Command genome" in line and "Sscrofa11.1_with_ERCC" in line for line in command_params)
    assert any("Annotation mode" in line and "Gencode" in line for line in command_params)
    assert not any("UMI" in line for line in command_params)
    assert "nf-core/rnaseq" in command_block
    assert "--genome Sscrofa11.1_with_ERCC" in command_block


def main() -> int:
    test_generation_with_runtime_command()
    test_dgea_label_and_software_version_fallback()
    test_ercc_catalog_entry_shapes_methods_text()
    test_run_sh_resolves_project_dir_from_linkar_runtime_copy()
    test_llm_config_resolution()
    test_project_api_metadata_resolution_and_rendering()
    test_nfcore_reference_and_command_details_ignore_project_umi()
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    catalog_text = (TEMPLATE_DIR / "methods_catalog.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    pixi_text = (TEMPLATE_DIR / "pixi.toml").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    assert "entry: run.sh" in template_text
    assert "llm_config:" in template_text
    assert "metadata_api_url:" in template_text
    assert "runtime_command.json" in readme_text
    assert "nfcore_methylseq:" in catalog_text
    assert "methylation_array_analysis:" in catalog_text
    assert "scverse_scrna_prep:" in catalog_text
    assert "minfi:" in catalog_text
    assert "scanpy:" in catalog_text
    assert 'exec python3 "${script_dir}/run.py"' in run_sh_text
    assert '--metadata-api-url "${METADATA_API_URL:-}"' in run_sh_text
    assert 'run-local = "python3 run.py"' in pixi_text
    assert 'test = "python3 test.py"' in pixi_text
    assert "resolve_llm_settings" in run_py_text
    assert "load_runtime_command" in run_py_text
    assert "resolve_project_api_metadata" in run_py_text
    print("methods template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
