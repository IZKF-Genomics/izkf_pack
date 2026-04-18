#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
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
        assert "cellranger-atac count --id sample_a" in long_text
        assert "example_reference" in long_text
        assert "cellranger-atac 2.2.0" in long_text
        assert "1 recorded workflow" in short_text
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
        assert "quarto: 1.6.0" in long_text
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
        assert "Salmon quantification outputs" in long_text
        assert "Synthetic spike-in standards for RNA-seq experiments" in refs
        assert context["runs"][0]["label"] == "ERCC spike-in quality control"
        assert context["runs"][0]["catalog"]["method_core"]


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
            llm_config="",
            llm_base_url="",
            llm_model="",
            llm_temperature=0.2,
        )
        env_before = {
            "ALT_OPENAI_KEY": os.environ.get("ALT_OPENAI_KEY"),
            "LINKAR_LLM_BASE_URL": os.environ.get("LINKAR_LLM_BASE_URL"),
            "LINKAR_LLM_MODEL": os.environ.get("LINKAR_LLM_MODEL"),
        }
        os.environ["ALT_OPENAI_KEY"] = "test-secret"
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


def main() -> int:
    test_generation_with_runtime_command()
    test_dgea_label_and_software_version_fallback()
    test_ercc_catalog_entry_shapes_methods_text()
    test_llm_config_resolution()
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    catalog_text = (TEMPLATE_DIR / "methods_catalog.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    pixi_text = (TEMPLATE_DIR / "pixi.toml").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    assert "entry: run.sh" in template_text
    assert "llm_config:" in template_text
    assert "runtime_command.json" in readme_text
    assert "nfcore_methylseq:" in catalog_text
    assert 'exec python3 "${script_dir}/run.py"' in run_sh_text
    assert 'run-local = "python3 run.py"' in pixi_text
    assert 'test = "python3 test.py"' in pixi_text
    assert "resolve_llm_settings" in run_py_text
    assert "load_runtime_command" in run_py_text
    print("methods template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
