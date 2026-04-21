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
NOTEBOOK_PATH = TEMPLATE_DIR / "annotation.qmd"
SOFTWARE_VERSIONS_SPEC = TEMPLATE_DIR / "assets" / "software_versions_spec.yaml"
PROJECT_CONFIG_PATH = CONFIG_DIR / "project.toml"
RUN_INFO_PATH = RESULTS_DIR / "run_info.yaml"
PIPELINE_SCRIPT = TEMPLATE_DIR / "build_annotation_outputs.py"


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
        "annotation_method": env("ANNOTATION_METHOD", "celltypist"),
        "annotation_methods": env("ANNOTATION_METHODS"),
        "celltypist_model": env("CELLTYPIST_MODEL"),
        "celltypist_mode": env("CELLTYPIST_MODE", "best_match"),
        "celltypist_p_thres": env("CELLTYPIST_P_THRES", "0.5"),
        "use_gpu": env("USE_GPU", "false"),
        "cluster_key": env("CLUSTER_KEY", "leiden"),
        "batch_key": env("BATCH_KEY", "batch"),
        "condition_key": env("CONDITION_KEY", "condition"),
        "sample_id_key": env("SAMPLE_ID_KEY", "sample_id"),
        "sample_label_key": env("SAMPLE_LABEL_KEY", "sample_display"),
        "majority_vote_min_fraction": env("MAJORITY_VOTE_MIN_FRACTION", "0.6"),
        "confidence_threshold": env("CONFIDENCE_THRESHOLD", "0.5"),
        "unknown_label": env("UNKNOWN_LABEL", "Unknown"),
        "predicted_label_key": env("PREDICTED_LABEL_KEY", "predicted_label"),
        "final_label_key": env("FINAL_LABEL_KEY", "final_label"),
        "marker_file": env("MARKER_FILE"),
        "rank_top_markers": env("RANK_TOP_MARKERS", "5"),
        "random_seed": env("RANDOM_SEED", "0"),
    }


def validate_params(params: dict[str, str]) -> None:
    if not params["input_h5ad"].strip():
        raise SystemExit("Set INPUT_H5AD or rely on a bound upstream scverse single-cell output before running scverse_scrna_annotate.")
    method = params["annotation_method"].strip().lower()
    raw_methods = params["annotation_methods"].strip()
    selected_methods = [item.strip().lower() for item in raw_methods.split(",") if item.strip()] if raw_methods else [method]
    if not selected_methods:
        selected_methods = [method]
    unsupported = sorted(set(selected_methods) - {"celltypist"})
    if unsupported:
        raise SystemExit("Set ANNOTATION_METHODS to supported values only. Currently implemented: celltypist.")
    if method not in {"celltypist"}:
        raise SystemExit("Set ANNOTATION_METHOD=celltypist. Additional annotation backends are not implemented yet.")
    if not params["celltypist_model"].strip():
        raise SystemExit("Set CELLTYPIST_MODEL to a relevant built-in model name or a custom model path before running scverse_scrna_annotate.")
    if not params["cluster_key"].strip():
        raise SystemExit("Set CLUSTER_KEY to the obs column that defines the review clusters.")
    mode = params["celltypist_mode"].strip().lower().replace(" ", "_")
    if mode not in {"best_match", "prob_match"}:
        raise SystemExit("Set CELLTYPIST_MODE to either best_match or prob_match.")


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
        f"cluster_key = {toml_string(params['cluster_key'])}",
        f"batch_key = {toml_string(params['batch_key'])}",
        f"condition_key = {toml_string(params['condition_key'])}",
        f"sample_id_key = {toml_string(params['sample_id_key'])}",
        f"sample_label_key = {toml_string(params['sample_label_key'])}",
        "",
        "[annotation]",
        f"annotation_method = {toml_string(params['annotation_method'])}",
        f"annotation_methods = {toml_string(params['annotation_methods'])}",
        f"celltypist_model = {toml_string(params['celltypist_model'])}",
        f"celltypist_mode = {toml_string(params['celltypist_mode'])}",
        f"celltypist_p_thres = {params['celltypist_p_thres']}",
        f"use_gpu = {'true' if parse_bool(params['use_gpu']) else 'false'}",
        f"majority_vote_min_fraction = {params['majority_vote_min_fraction']}",
        f"confidence_threshold = {params['confidence_threshold']}",
        f"unknown_label = {toml_string(params['unknown_label'])}",
        f"predicted_label_key = {toml_string(params['predicted_label_key'])}",
        f"final_label_key = {toml_string(params['final_label_key'])}",
        f"marker_file = {toml_string(params['marker_file'])}",
        f"rank_top_markers = {params['rank_top_markers']}",
        f"random_seed = {params['random_seed']}",
        "",
        "[output]",
        'adata_file = "results/adata.annotated.h5ad"',
        'cell_annotation_predictions_file = "results/tables/cell_annotation_predictions.csv"',
        'cluster_annotation_summary_file = "results/tables/cluster_annotation_summary.csv"',
        'marker_review_summary_file = "results/tables/marker_review_summary.csv"',
        'annotation_status_summary_file = "results/tables/annotation_status_summary.csv"',
        'method_comparison_file = "results/tables/method_comparison.csv"',
        'report_context_file = "results/report_context.yaml"',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_run_info(path: Path, params: dict[str, str], *, project_name: str) -> None:
    bool_keys = {"use_gpu"}
    payload = {
        "workspace_dir": str(TEMPLATE_DIR),
        "project_dir": str(PROJECT_DIR),
        "results_dir": str(RESULTS_DIR),
        "params": {
            "project_name": project_name,
            **{key: (parse_bool(value) if key in bool_keys else value) for key, value in params.items()},
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
    run_command(["pixi", "run", "python", str(PIPELINE_SCRIPT)])
    report_files = ["annotation_overview.qmd"]
    raw_methods = params["annotation_methods"].strip()
    selected_methods = [item.strip().lower() for item in raw_methods.split(",") if item.strip()] if raw_methods else [params["annotation_method"].strip().lower()]
    if "celltypist" in selected_methods:
        report_files.append("celltypist.qmd")
    for report_name in report_files:
        run_command(
            [
                "pixi",
                "run",
                "quarto",
                "render",
                str(TEMPLATE_DIR / report_name),
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
