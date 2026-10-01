#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent


def load_configure():
    spec = importlib.util.spec_from_file_location("configure_analysis", ROOT / "configure_analysis.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def sample_rows() -> list[dict[str, str]]:
    output = []
    for genotype, count in (("WT", 2), ("TTN", 4)):
        for index in range(1, count + 1):
            for condition in ("Control", "SinusRhythm", "AtrialFibrillation"):
                output.append({"sample": f"{genotype}{index}_{condition}", "group": f"{genotype}_{condition}", "id": f"{genotype}{index}"})
    return output


def test_configuration_and_validation() -> None:
    module = load_configure()
    rows = sample_rows()
    metadata = module.infer_metadata(["sample", "group", "id"], rows)
    config = module.default_configuration(metadata)
    assert [x["id"] for x in config["contrasts"]] == [
        "baseline_ttn", "wt_sr_vs_control", "ttn_sr_vs_control", "ttn_sr_response_interaction",
        "wt_af_vs_sr", "ttn_af_vs_sr", "ttn_af_response_interaction",
    ]
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        sheet, samples, config_path, salmon = root / "samplesheet.csv", root / "samples.csv", root / "analysis.yaml", root / "salmon"
        with sheet.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["sample", "group", "id"])
            writer.writeheader(); writer.writerows(rows)
        module.write_metadata(samples, metadata)
        module.write_config(config_path, config)
        for row in metadata:
            path = salmon / row["sample"] / "quant.sf"
            path.parent.mkdir(parents=True)
            path.write_text("Name\tLength\tEffectiveLength\tTPM\tNumReads\n")
        module.validate(sheet, salmon, config_path, samples)


def test_static_contract() -> None:
    functions = (ROOT / "DGEA_functions.R").read_text()
    constructor = (ROOT / "DGEA_constructor.R").read_text()
    run = (ROOT / "run.sh").read_text()
    assert "assert_full_rank" in functions
    assert "~ subject_nested + condition + genotype_condition_interaction" in functions
    assert "interaction_significant" in functions and "response_class" in functions
    assert "run_pathway_analysis" in constructor
    assert "dpi = 450" in functions and "gene_symbol" in functions
    assert "write_comparison_workbooks" in constructor
    assert run.index("DGEA_constructor.R") < run.index("build_interpretation.py") < run.index("render_reports.py")
    manifest = yaml.safe_load((ROOT / "linkar_template.yaml").read_text())
    assert manifest["id"] == "dgea_interaction"
    assert manifest["run"]["mode"] == "render"


def test_deterministic_interpretation() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); tables = root / "tables"; tables.mkdir(parents=True); (tables / "pathways").mkdir()
        config = load_configure().default_configuration(load_configure().infer_metadata(["sample", "group", "id"], sample_rows()))
        config_path = root / "analysis.yaml"; config_path.write_text(yaml.safe_dump(config, sort_keys=False))
        with (tables / "contrast_summary.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["contrast_id", "n_fdr_significant", "n_evidence_threshold"]); writer.writeheader()
            for contrast in config["contrasts"]: writer.writerow({"contrast_id": contrast["id"], "n_fdr_significant": 1, "n_evidence_threshold": 1})
        (tables / "response_class_summary.csv").write_text("interaction_id,response_class,n_genes\nttn_af_response_interaction,enhanced_response,1\n")
        (tables / "pathways" / "status.csv").write_text("contrast_id,pathways_fdr\nttn_af_response_interaction,2\n")
        subprocess.run(["python3", str(ROOT / "build_interpretation.py"), "--results-dir", str(root), "--config", str(config_path), "--use-llm", "false"], check=True)
        response = json.loads((root / "interpretation_response.json").read_text())
        assert response["used_llm"] is False
        text = (root / "interpretation.md").read_text()
        assert "unequal within-genotype DEG" not in text
        assert "direct test" in text and "Where to find response-pattern details" in text


if __name__ == "__main__":
    test_configuration_and_validation()
    test_static_contract()
    test_deterministic_interpretation()
    print("dgea_interaction tests passed")
