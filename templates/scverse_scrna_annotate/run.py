#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import shutil
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
PACK_ROOT = Path(os.environ.get("LINKAR_PACK_ROOT", TEMPLATE_DIR.parent.parent)).resolve()
PROJECT_DIR = Path(os.environ.get("LINKAR_PROJECT_DIR", TEMPLATE_DIR.parent)).resolve()
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
REPORTS_DIR = TEMPLATE_DIR / "reports"
CONFIG_DIR = TEMPLATE_DIR / "config"
SOFTWARE_VERSIONS_SPEC = TEMPLATE_DIR / "assets" / "software_versions_spec.yaml"
USER_CONFIG_TEMPLATE_PATH = TEMPLATE_DIR / "assets" / "annotation_config.template.yaml"
DEFAULT_USER_CONFIG_PATH = CONFIG_DIR / "annotation_config.yaml"
RESOLVED_USER_CONFIG_PATH = CONFIG_DIR / "annotation_config.resolved.yaml"
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


def default_params() -> dict[str, str]:
    return {
        "annotation_config": str(DEFAULT_USER_CONFIG_PATH),
        "input_h5ad": "",
        "input_source_template": "",
        "annotation_method": "celltypist",
        "annotation_methods": "celltypist",
        "celltypist_model": "",
        "celltypist_mode": "best_match",
        "celltypist_p_thres": "0.5",
        "use_gpu": "false",
        "cluster_key": "leiden",
        "batch_key": "batch",
        "condition_key": "condition",
        "sample_id_key": "sample_id",
        "sample_label_key": "sample_display",
        "majority_vote_min_fraction": "0.6",
        "confidence_threshold": "0.5",
        "unknown_label": "Unknown",
        "predicted_label_key": "predicted_label",
        "final_label_key": "final_label",
        "marker_file": "",
        "rank_top_markers": "5",
        "random_seed": "0",
    }


def env_params() -> dict[str, str]:
    return {
        "annotation_config": env("ANNOTATION_CONFIG"),
        "input_h5ad": env("INPUT_H5AD"),
        "input_source_template": env("INPUT_SOURCE_TEMPLATE"),
        "annotation_method": env("ANNOTATION_METHOD"),
        "annotation_methods": env("ANNOTATION_METHODS"),
        "celltypist_model": env("CELLTYPIST_MODEL"),
        "celltypist_mode": env("CELLTYPIST_MODE"),
        "celltypist_p_thres": env("CELLTYPIST_P_THRES"),
        "use_gpu": env("USE_GPU"),
        "cluster_key": env("CLUSTER_KEY"),
        "batch_key": env("BATCH_KEY"),
        "condition_key": env("CONDITION_KEY"),
        "sample_id_key": env("SAMPLE_ID_KEY"),
        "sample_label_key": env("SAMPLE_LABEL_KEY"),
        "majority_vote_min_fraction": env("MAJORITY_VOTE_MIN_FRACTION"),
        "confidence_threshold": env("CONFIDENCE_THRESHOLD"),
        "unknown_label": env("UNKNOWN_LABEL"),
        "predicted_label_key": env("PREDICTED_LABEL_KEY"),
        "final_label_key": env("FINAL_LABEL_KEY"),
        "marker_file": env("MARKER_FILE"),
        "rank_top_markers": env("RANK_TOP_MARKERS"),
        "random_seed": env("RANDOM_SEED"),
    }


def normalize_annotation_methods(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value).strip()


def normalize_bool_string(value: object) -> str:
    return "true" if parse_bool(str(value)) else "false"


def read_annotation_config(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SystemExit(f"Annotation config must be a YAML mapping: {path}")
    return payload


def flatten_annotation_config(payload: dict[str, object]) -> dict[str, str]:
    global_cfg = payload.get("global") if isinstance(payload.get("global"), dict) else {}
    celltypist_cfg = payload.get("celltypist") if isinstance(payload.get("celltypist"), dict) else {}
    marker_cfg = payload.get("marker_review") if isinstance(payload.get("marker_review"), dict) else {}

    annotation_methods = normalize_annotation_methods(
        global_cfg.get("annotation_methods", payload.get("annotation_methods", ""))
    )
    annotation_method = str(
        global_cfg.get(
            "annotation_method",
            payload.get("annotation_method", annotation_methods.split(",")[0] if annotation_methods else ""),
        )
    ).strip()

    flat: dict[str, str] = {
        "annotation_config": str(payload.get("_config_path", "")),
        "input_h5ad": str(global_cfg.get("input_h5ad", payload.get("input_h5ad", ""))).strip(),
        "input_source_template": str(
            global_cfg.get("input_source_template", payload.get("input_source_template", ""))
        ).strip(),
        "annotation_method": annotation_method,
        "annotation_methods": annotation_methods,
        "celltypist_model": str(celltypist_cfg.get("model", payload.get("celltypist_model", ""))).strip(),
        "celltypist_mode": str(celltypist_cfg.get("mode", payload.get("celltypist_mode", ""))).strip(),
        "celltypist_p_thres": str(celltypist_cfg.get("p_thres", payload.get("celltypist_p_thres", ""))).strip(),
        "use_gpu": normalize_bool_string(celltypist_cfg.get("use_gpu", payload.get("use_gpu", False))),
        "cluster_key": str(global_cfg.get("cluster_key", payload.get("cluster_key", ""))).strip(),
        "batch_key": str(global_cfg.get("batch_key", payload.get("batch_key", ""))).strip(),
        "condition_key": str(global_cfg.get("condition_key", payload.get("condition_key", ""))).strip(),
        "sample_id_key": str(global_cfg.get("sample_id_key", payload.get("sample_id_key", ""))).strip(),
        "sample_label_key": str(global_cfg.get("sample_label_key", payload.get("sample_label_key", ""))).strip(),
        "majority_vote_min_fraction": str(
            global_cfg.get("majority_vote_min_fraction", payload.get("majority_vote_min_fraction", ""))
        ).strip(),
        "confidence_threshold": str(
            global_cfg.get("confidence_threshold", payload.get("confidence_threshold", ""))
        ).strip(),
        "unknown_label": str(global_cfg.get("unknown_label", payload.get("unknown_label", ""))).strip(),
        "predicted_label_key": str(
            global_cfg.get("predicted_label_key", payload.get("predicted_label_key", ""))
        ).strip(),
        "final_label_key": str(global_cfg.get("final_label_key", payload.get("final_label_key", ""))).strip(),
        "marker_file": str(marker_cfg.get("marker_file", payload.get("marker_file", ""))).strip(),
        "rank_top_markers": str(global_cfg.get("rank_top_markers", payload.get("rank_top_markers", ""))).strip(),
        "random_seed": str(global_cfg.get("random_seed", payload.get("random_seed", ""))).strip(),
    }
    return flat


def resolve_annotation_config_path() -> Path:
    raw = env("ANNOTATION_CONFIG").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_USER_CONFIG_PATH.resolve()


def ensure_default_annotation_config(path: Path) -> None:
    if path != DEFAULT_USER_CONFIG_PATH.resolve():
        return
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(USER_CONFIG_TEMPLATE_PATH, path)


def merge_params(base: dict[str, str], updates: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    for key, value in updates.items():
        if value is None:
            continue
        text = str(value)
        if text == "":
            continue
        merged[key] = text
    return merged


def resolved_params() -> dict[str, str]:
    params = default_params()
    config_path = resolve_annotation_config_path()
    ensure_default_annotation_config(config_path)
    config_payload = read_annotation_config(config_path)
    if config_payload:
        config_payload["_config_path"] = str(config_path)
        params = merge_params(params, flatten_annotation_config(config_payload))
    params = merge_params(params, env_params())
    if not params["annotation_config"].strip():
        params["annotation_config"] = str(config_path)
    if not params["annotation_methods"].strip():
        params["annotation_methods"] = params["annotation_method"].strip() or "celltypist"
    if not params["annotation_method"].strip():
        params["annotation_method"] = params["annotation_methods"].split(",")[0].strip() or "celltypist"
    return params


def validate_params(params: dict[str, str]) -> None:
    if not params["input_h5ad"].strip():
        raise SystemExit(
            "Set INPUT_H5AD or fill global.input_h5ad in config/annotation_config.yaml before running scverse_scrna_annotate."
        )
    method = params["annotation_method"].strip().lower()
    raw_methods = params["annotation_methods"].strip()
    selected_methods = [item.strip().lower() for item in raw_methods.split(",") if item.strip()] if raw_methods else [method]
    if not selected_methods:
        selected_methods = [method]
    unsupported = sorted(set(selected_methods) - {"celltypist"})
    if unsupported:
        raise SystemExit(
            "Set ANNOTATION_METHODS or global.annotation_methods to supported values only. Currently implemented: celltypist."
        )
    if method not in {"celltypist"}:
        raise SystemExit(
            "Set ANNOTATION_METHOD or global.annotation_method to celltypist. Additional annotation backends are not implemented yet."
        )
    if not params["celltypist_model"].strip():
        raise SystemExit(
            "Set CELLTYPIST_MODEL or celltypist.model to a relevant built-in model name or a custom model path before running scverse_scrna_annotate."
        )
    if not params["cluster_key"].strip():
        raise SystemExit("Set CLUSTER_KEY or global.cluster_key to the obs column that defines the review clusters.")
    mode = params["celltypist_mode"].strip().lower().replace(" ", "_")
    if mode not in {"best_match", "prob_match"}:
        raise SystemExit("Set CELLTYPIST_MODE or celltypist.mode to either best_match or prob_match.")


def write_resolved_annotation_config(path: Path, params: dict[str, str]) -> None:
    payload = {
        "global": {
            "input_h5ad": params["input_h5ad"],
            "input_source_template": params["input_source_template"],
            "annotation_method": params["annotation_method"],
            "annotation_methods": [item.strip() for item in params["annotation_methods"].split(",") if item.strip()],
            "cluster_key": params["cluster_key"],
            "batch_key": params["batch_key"],
            "condition_key": params["condition_key"],
            "sample_id_key": params["sample_id_key"],
            "sample_label_key": params["sample_label_key"],
            "majority_vote_min_fraction": float(params["majority_vote_min_fraction"]),
            "confidence_threshold": float(params["confidence_threshold"]),
            "unknown_label": params["unknown_label"],
            "predicted_label_key": params["predicted_label_key"],
            "final_label_key": params["final_label_key"],
            "rank_top_markers": int(params["rank_top_markers"]),
            "random_seed": int(params["random_seed"]),
        },
        "celltypist": {
            "model": params["celltypist_model"],
            "mode": params["celltypist_mode"],
            "p_thres": float(params["celltypist_p_thres"]),
            "use_gpu": parse_bool(params["use_gpu"]),
        },
        "marker_review": {
            "marker_file": params["marker_file"],
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


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
        "annotation_config": params["annotation_config"],
        "resolved_annotation_config": str(RESOLVED_USER_CONFIG_PATH),
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
    write_resolved_annotation_config(RESOLVED_USER_CONFIG_PATH, params)
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
