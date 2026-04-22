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
NOTEBOOK_PATH = TEMPLATE_DIR / "scrna_integrate.qmd"
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
        "input_source_template": env("INPUT_SOURCE_TEMPLATE"),
        "integration_method": env("INTEGRATION_METHOD", "scvi"),
        "batch_key": env("BATCH_KEY", "batch"),
        "condition_key": env("CONDITION_KEY", "condition"),
        "sample_id_key": env("SAMPLE_ID_KEY", "sample_id"),
        "sample_label_key": env("SAMPLE_LABEL_KEY", "sample_display"),
        "label_key_for_metrics": env("LABEL_KEY_FOR_METRICS"),
        "run_scib_metrics": env("RUN_SCIB_METRICS", "true"),
        "use_hvgs_only": env("USE_HVGS_ONLY", "true"),
        "n_top_hvgs": env("N_TOP_HVGS", "3000"),
        "n_pcs": env("N_PCS", "30"),
        "n_neighbors": env("N_NEIGHBORS", "15"),
        "umap_min_dist": env("UMAP_MIN_DIST", "0.5"),
        "cluster_resolution": env("CLUSTER_RESOLUTION", "0.8"),
        "random_seed": env("RANDOM_SEED", "0"),
        "harmony_theta": env("HARMONY_THETA", "2.0"),
        "harmony_lambda": env("HARMONY_LAMBDA", "1.0"),
        "harmony_max_iter": env("HARMONY_MAX_ITER", "20"),
        "bbknn_neighbors_within_batch": env("BBKNN_NEIGHBORS_WITHIN_BATCH", "3"),
        "bbknn_trim": env("BBKNN_TRIM", "0"),
        "scanvi_label_key": env("SCANVI_LABEL_KEY"),
        "scanvi_unlabeled_category": env("SCANVI_UNLABELED_CATEGORY", "Unknown"),
        "scvi_latent_dim": env("SCVI_LATENT_DIM", "30"),
        "scvi_max_epochs": env("SCVI_MAX_EPOCHS", "200"),
        "scvi_gene_likelihood": env("SCVI_GENE_LIKELIHOOD", "zinb"),
        "scvi_accelerator": env("SCVI_ACCELERATOR", "auto"),
        "scvi_devices": env("SCVI_DEVICES", "1"),
    }


def validate_params(params: dict[str, str]) -> None:
    if not params["input_h5ad"].strip():
        raise SystemExit("Set INPUT_H5AD or rely on a bound upstream scrna_prep output before running scrna_integrate.")
    if not params["batch_key"].strip():
        raise SystemExit("Set BATCH_KEY to the obs column that defines the integration batch.")
    method = params["integration_method"].strip().lower()
    allowed = {"scvi", "scanvi", "harmony", "bbknn", "scanorama"}
    if method not in allowed:
        raise SystemExit("Set INTEGRATION_METHOD to one of: bbknn, harmony, scanorama, scanvi, scvi.")
    if method == "scanvi" and not params["scanvi_label_key"].strip():
        raise SystemExit("Set SCANVI_LABEL_KEY when INTEGRATION_METHOD=scanvi.")


def write_project_config(path: Path, params: dict[str, str], *, project_name: str) -> None:
    lines = [
        "[project]",
        f"name = {toml_string(project_name)}",
        "",
        "[input]",
        f"input_h5ad = {toml_string(params['input_h5ad'])}",
        f"input_source_template = {toml_string(params['input_source_template'])}",
        "",
        "[metadata]",
        f"batch_key = {toml_string(params['batch_key'])}",
        f"condition_key = {toml_string(params['condition_key'])}",
        f"sample_id_key = {toml_string(params['sample_id_key'])}",
        f"sample_label_key = {toml_string(params['sample_label_key'])}",
        f"label_key_for_metrics = {toml_string(params['label_key_for_metrics'])}",
        "",
        "[integration]",
        f"integration_method = {toml_string(params['integration_method'])}",
        f"run_scib_metrics = {'true' if parse_bool(params['run_scib_metrics']) else 'false'}",
        f"use_hvgs_only = {'true' if parse_bool(params['use_hvgs_only']) else 'false'}",
        f"n_top_hvgs = {params['n_top_hvgs']}",
        f"n_pcs = {params['n_pcs']}",
        f"n_neighbors = {params['n_neighbors']}",
        f"umap_min_dist = {params['umap_min_dist']}",
        f"cluster_resolution = {params['cluster_resolution']}",
        f"random_seed = {params['random_seed']}",
        f"harmony_theta = {params['harmony_theta']}",
        f"harmony_lambda = {params['harmony_lambda']}",
        f"harmony_max_iter = {params['harmony_max_iter']}",
        f"bbknn_neighbors_within_batch = {params['bbknn_neighbors_within_batch']}",
        f"bbknn_trim = {params['bbknn_trim']}",
        f"scanvi_label_key = {toml_string(params['scanvi_label_key'])}",
        f"scanvi_unlabeled_category = {toml_string(params['scanvi_unlabeled_category'])}",
        f"scvi_latent_dim = {params['scvi_latent_dim']}",
        f"scvi_max_epochs = {params['scvi_max_epochs']}",
        f"scvi_gene_likelihood = {toml_string(params['scvi_gene_likelihood'])}",
        f"scvi_accelerator = {toml_string(params['scvi_accelerator'])}",
        f"scvi_devices = {params['scvi_devices']}",
        "",
        "[output]",
        'adata_file = "results/adata.integrated.h5ad"',
        'integration_summary_file = "results/tables/integration_summary.csv"',
        'integration_metrics_file = "results/tables/integration_metrics.csv"',
        'batch_mixing_summary_file = "results/tables/batch_mixing_summary.csv"',
        'cluster_counts_file = "results/tables/cluster_counts.csv"',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_run_info(path: Path, params: dict[str, str], *, project_name: str) -> None:
    payload = {
        "workspace_dir": str(TEMPLATE_DIR),
        "project_dir": str(PROJECT_DIR),
        "results_dir": str(RESULTS_DIR),
        "params": {
            "project_name": project_name,
            **{
                key: (parse_bool(value) if key in {"run_scib_metrics", "use_hvgs_only"} else value)
                for key, value in params.items()
            },
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
    write_project_config(PROJECT_CONFIG_PATH, params, project_name=project_name)
    write_run_info(RUN_INFO_PATH, params, project_name=project_name)

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
