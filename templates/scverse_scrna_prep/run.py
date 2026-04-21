#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
PACK_ROOT = Path(os.environ.get("LINKAR_PACK_ROOT", TEMPLATE_DIR.parent.parent)).resolve()
PROJECT_DIR = Path(os.environ.get("LINKAR_PROJECT_DIR", TEMPLATE_DIR.parent)).resolve()
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
REPORTS_DIR = TEMPLATE_DIR / "reports"
CONFIG_DIR = TEMPLATE_DIR / "config"
NOTEBOOK_PATH = TEMPLATE_DIR / "qc.qmd"
SOFTWARE_VERSIONS_SPEC = TEMPLATE_DIR / "assets" / "software_versions_spec.yaml"
PROJECT_CONFIG_PATH = CONFIG_DIR / "project.toml"
RUN_INFO_PATH = RESULTS_DIR / "run_info.yaml"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def resolved_params() -> dict[str, str]:
    return {
        "input_h5ad": env("INPUT_H5AD"),
        "input_matrix": env("INPUT_MATRIX"),
        "input_source_template": env("INPUT_SOURCE_TEMPLATE"),
        "ambient_correction_applied": env("AMBIENT_CORRECTION_APPLIED", "false"),
        "ambient_correction_method": env("AMBIENT_CORRECTION_METHOD", "none"),
        "input_format": env("INPUT_FORMAT", "auto"),
        "var_names": env("VAR_NAMES", "gene_symbols"),
        "sample_metadata": env("SAMPLE_METADATA"),
        "organism": env("ORGANISM"),
        "batch_key": env("BATCH_KEY", "batch"),
        "condition_key": env("CONDITION_KEY", "condition"),
        "sample_id_key": env("SAMPLE_ID_KEY", "sample_id"),
        "doublet_method": env("DOUBLET_METHOD", "none"),
        "filter_predicted_doublets": env("FILTER_PREDICTED_DOUBLETS", "false"),
        "qc_mode": env("QC_MODE", "fixed"),
        "qc_nmads": env("QC_NMADS", "3.0"),
        "min_genes": env("MIN_GENES", "200"),
        "min_cells": env("MIN_CELLS", "3"),
        "min_counts": env("MIN_COUNTS", "500"),
        "max_pct_counts_mt": env("MAX_PCT_COUNTS_MT", "20.0"),
        "max_pct_counts_ribo": env("MAX_PCT_COUNTS_RIBO"),
        "max_pct_counts_hb": env("MAX_PCT_COUNTS_HB"),
        "n_top_hvgs": env("N_TOP_HVGS", "3000"),
        "n_pcs": env("N_PCS", "30"),
        "n_neighbors": env("N_NEIGHBORS", "15"),
        "leiden_resolution": env("LEIDEN_RESOLUTION"),
        "resolution_grid": env("RESOLUTION_GRID", "0.2,0.4,0.6,0.8,1.0,1.2"),
    }


def validate_params(params: dict[str, str]) -> None:
    if not params["input_h5ad"].strip() and not params["input_matrix"].strip():
        raise SystemExit("Set either INPUT_H5AD or INPUT_MATRIX before running scverse_scrna_prep.")
    if not params["organism"].strip():
        raise SystemExit("Set ORGANISM to a supported value such as human, mouse, hsapiens, or mmusculus.")


def write_project_config(path: Path, params: dict[str, str], *, project_name: str, sample_metadata: str) -> None:
    lines = [
        "[project]",
        f"name = {toml_string(project_name)}",
        "",
        "[input]",
        f"input_h5ad = {toml_string(params['input_h5ad'])}",
        f"input_matrix = {toml_string(params['input_matrix'])}",
        f"input_source_template = {toml_string(params['input_source_template'])}",
        f"ambient_correction_applied = {'true' if parse_bool(params['ambient_correction_applied']) else 'false'}",
        f"ambient_correction_method = {toml_string(params['ambient_correction_method'])}",
        f"input_format = {toml_string(params['input_format'])}",
        f"var_names = {toml_string(params['var_names'])}",
        f"sample_metadata = {toml_string(sample_metadata)}",
        "",
        "[metadata]",
        f"organism = {toml_string(params['organism'])}",
        f"sample_id_key = {toml_string(params['sample_id_key'])}",
        f"batch_key = {toml_string(params['batch_key'])}",
        f"condition_key = {toml_string(params['condition_key'])}",
        "",
        "[qc]",
        f"doublet_method = {toml_string(params['doublet_method'])}",
        f"filter_predicted_doublets = {'true' if parse_bool(params['filter_predicted_doublets']) else 'false'}",
        f"qc_mode = {toml_string(params['qc_mode'])}",
        f"qc_nmads = {params['qc_nmads']}",
        f"min_genes = {params['min_genes']}",
        f"min_cells = {params['min_cells']}",
        f"min_counts = {params['min_counts']}",
        f"max_pct_counts_mt = {params['max_pct_counts_mt']}",
        f"max_pct_counts_ribo = {toml_string(params['max_pct_counts_ribo'])}",
        f"max_pct_counts_hb = {toml_string(params['max_pct_counts_hb'])}",
        "",
        "[analysis]",
        f"n_top_hvgs = {params['n_top_hvgs']}",
        f"n_pcs = {params['n_pcs']}",
        f"n_neighbors = {params['n_neighbors']}",
        f"leiden_resolution = {toml_string(params['leiden_resolution'])}",
        f"resolution_grid = {toml_string(params['resolution_grid'])}",
        "target_sum = 10000",
        "",
        "[output]",
        'adata_file = "results/adata.prep.h5ad"',
        'qc_summary_file = "results/tables/qc_summary.csv"',
        'sample_qc_summary_file = "results/tables/sample_qc_summary.csv"',
        'cluster_counts_file = "results/tables/cluster_counts.csv"',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_run_info(path: Path, params: dict[str, str], *, project_name: str, sample_metadata: str) -> None:
    payload = {
        "workspace_dir": str(TEMPLATE_DIR),
        "project_dir": str(PROJECT_DIR),
        "results_dir": str(RESULTS_DIR),
        "params": {
            "project_name": project_name,
            "input_h5ad": params["input_h5ad"],
            "input_matrix": params["input_matrix"],
            "input_source_template": params["input_source_template"],
            "ambient_correction_applied": parse_bool(params["ambient_correction_applied"]),
            "ambient_correction_method": params["ambient_correction_method"],
            "input_format": params["input_format"],
            "var_names": params["var_names"],
            "sample_metadata": sample_metadata,
            "organism": params["organism"],
            "sample_id_key": params["sample_id_key"],
            "batch_key": params["batch_key"],
            "condition_key": params["condition_key"],
            "doublet_method": params["doublet_method"],
            "filter_predicted_doublets": parse_bool(params["filter_predicted_doublets"]),
            "qc_mode": params["qc_mode"],
            "qc_nmads": params["qc_nmads"],
            "min_genes": params["min_genes"],
            "min_cells": params["min_cells"],
            "min_counts": params["min_counts"],
            "max_pct_counts_mt": params["max_pct_counts_mt"],
            "max_pct_counts_ribo": params["max_pct_counts_ribo"],
            "max_pct_counts_hb": params["max_pct_counts_hb"],
            "n_top_hvgs": params["n_top_hvgs"],
            "n_pcs": params["n_pcs"],
            "n_neighbors": params["n_neighbors"],
            "leiden_resolution": params["leiden_resolution"],
            "resolution_grid": params["resolution_grid"],
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def run_command(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=TEMPLATE_DIR, check=True)


def main() -> int:
    params = resolved_params()
    validate_params(params)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    project_name = PROJECT_DIR.name
    sample_metadata = params["sample_metadata"].strip() or "assets/samples.csv"

    write_project_config(PROJECT_CONFIG_PATH, params, project_name=project_name, sample_metadata=sample_metadata)
    write_run_info(RUN_INFO_PATH, params, project_name=project_name, sample_metadata=sample_metadata)

    run_command(["pixi", "install"])
    run_command(
        [
            "pixi",
            "run",
            "quarto",
            "render",
            str(NOTEBOOK_PATH),
            "--to",
            "html",
            "--output-dir",
            str(REPORTS_DIR),
            "--no-clean",
        ]
    )
    run_command(
        [
            "python3",
            str(PACK_ROOT / "functions" / "software_versions.py"),
            "--spec",
            str(SOFTWARE_VERSIONS_SPEC),
            "--output",
            str(RESULTS_DIR / "software_versions.json"),
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
