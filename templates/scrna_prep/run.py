#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
NOTEBOOK_PATH = TEMPLATE_DIR / "scrna_prep.qmd"
SOFTWARE_VERSIONS_SPEC = TEMPLATE_DIR / "assets" / "software_versions_spec.yaml"
PROJECT_CONFIG_PATH = CONFIG_DIR / "project.toml"
RUN_INFO_PATH = RESULTS_DIR / "run_info.yaml"
SUPPORTED_ORGANISM_ALIASES = {
    "human": "human",
    "hsapiens": "human",
    "homo_sapiens": "human",
    "mouse": "mouse",
    "mmusculus": "mouse",
    "mus_musculus": "mouse",
}
SUPPORTED_ORGANISM_HELP = ", ".join(SUPPORTED_ORGANISM_ALIASES)
SUPPORTED_INPUT_FORMATS = (
    "auto",
    "h5ad",
    "10x_h5",
    "10x_mtx",
    "parsebio",
    "scalebio",
    "cellranger_per_sample_outs",
)
SUPPORTED_MATRIX_INPUT_FORMATS = tuple(fmt for fmt in SUPPORTED_INPUT_FORMATS if fmt not in {"auto", "h5ad"})
SUPPORTED_INPUT_FORMAT_HELP = ", ".join(SUPPORTED_INPUT_FORMATS)
SUPPORTED_MATRIX_INPUT_FORMAT_HELP = ", ".join(SUPPORTED_MATRIX_INPUT_FORMATS)
SUPPORTED_VAR_NAME_CHOICES = ("gene_symbols", "gene_ids")
SUPPORTED_VAR_NAME_HELP = ", ".join(SUPPORTED_VAR_NAME_CHOICES)
SUPPORTED_DOUBLET_METHODS = ("none", "scrublet")
SUPPORTED_QC_MODES = ("fixed", "mad_per_sample")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def resolve_runtime_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (TEMPLATE_DIR / path).resolve()


def first_existing(*paths: Path) -> Path | None:
    for candidate in paths:
        if candidate.exists():
            return candidate
    return None


def detect_input_format(path: Path) -> str:
    if path.is_dir():
        if path.name == "per_sample_outs":
            for child in sorted(path.iterdir()):
                if not child.is_dir():
                    continue
                count_dir = child / "count"
                if first_existing(
                    count_dir / "sample_filtered_feature_bc_matrix.h5",
                    count_dir / "sample_raw_feature_bc_matrix.h5",
                ):
                    return "cellranger_per_sample_outs"
        if first_existing(path / "count_matrix.mtx", path / "count_matrix.mtx.gz") and first_existing(
            path / "all_genes.csv", path / "all_genes.csv.gz"
        ):
            return "parsebio"
        if first_existing(path / "matrix.mtx", path / "matrix.mtx.gz") and first_existing(
            path / "features.tsv", path / "features.tsv.gz"
        ) and (
            "scalebio" in path.as_posix().lower()
            or "starsolo" in path.as_posix().lower()
        ):
            return "scalebio"
        if first_existing(path / "matrix.mtx", path / "matrix.mtx.gz") and first_existing(
            path / "features.tsv", path / "features.tsv.gz"
        ):
            return "10x_mtx"
        return ""
    lower = path.name.lower()
    if lower.endswith(".h5ad"):
        return "h5ad"
    if lower.endswith(".h5"):
        return "10x_h5"
    return ""


def require_int(name: str, raw: str, *, minimum: int = 0) -> None:
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise SystemExit(f"Set {name} to an integer value. Received: {raw}.") from exc
    if value < minimum:
        comparator = f"at least {minimum}"
        raise SystemExit(f"Set {name} to an integer value of {comparator}. Received: {value}.")


def require_float(name: str, raw: str, *, minimum: float | None = None, maximum: float | None = None) -> None:
    try:
        value = float(str(raw).strip())
    except ValueError as exc:
        raise SystemExit(f"Set {name} to a numeric value. Received: {raw}.") from exc
    if minimum is not None and value < minimum:
        raise SystemExit(f"Set {name} to a numeric value >= {minimum}. Received: {value}.")
    if maximum is not None and value > maximum:
        raise SystemExit(f"Set {name} to a numeric value <= {maximum}. Received: {value}.")


def require_optional_percent(name: str, raw: str) -> None:
    if not str(raw).strip():
        return
    require_float(name, raw, minimum=0.0, maximum=100.0)


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
    input_h5ad = params["input_h5ad"].strip()
    input_matrix = params["input_matrix"].strip()
    input_format = params["input_format"].strip().lower() or "auto"
    var_names = params["var_names"].strip() or "gene_symbols"
    doublet_method = params["doublet_method"].strip().lower() or "none"
    qc_mode = params["qc_mode"].strip().lower() or "fixed"

    if not input_h5ad and not input_matrix:
        raise SystemExit(
            "Set INPUT_H5AD or INPUT_MATRIX before running scrna_prep. "
            "For example, pass --input-h5ad /path/to/input.h5ad or --input-matrix /path/to/matrix_dir."
        )
    if input_h5ad and input_matrix:
        raise SystemExit(
            "Set only one of INPUT_H5AD or INPUT_MATRIX before running scrna_prep. "
            "Use INPUT_H5AD for AnnData .h5ad input and INPUT_MATRIX for matrix-style inputs such as "
            "Cell Ranger .h5, 10x MTX directories, ParseBio, ScaleBio, or per_sample_outs."
        )
    if input_format not in SUPPORTED_INPUT_FORMATS:
        raise SystemExit(
            f"Set INPUT_FORMAT to one of: {SUPPORTED_INPUT_FORMAT_HELP}. Received: {params['input_format'].strip() or '<empty>'}."
        )
    if var_names not in SUPPORTED_VAR_NAME_CHOICES:
        raise SystemExit(
            f"Set VAR_NAMES to one of: {SUPPORTED_VAR_NAME_HELP}. Received: {params['var_names'].strip() or '<empty>'}."
        )

    chosen_name = "INPUT_H5AD" if input_h5ad else "INPUT_MATRIX"
    chosen_value = input_h5ad or input_matrix
    chosen_path = resolve_runtime_path(chosen_value)
    if not chosen_path.exists():
        raise SystemExit(f"{chosen_name} does not exist: {chosen_path}.")

    detected_format = detect_input_format(chosen_path)
    if input_h5ad:
        if chosen_path.suffix.lower() != ".h5ad":
            raise SystemExit(f"INPUT_H5AD must point to a .h5ad file. Received: {chosen_path}.")
        if input_format not in {"auto", "h5ad"}:
            raise SystemExit(
                f"Use INPUT_FORMAT=auto or h5ad when INPUT_H5AD is set. Received: {input_format}."
            )
    else:
        if chosen_path.suffix.lower() == ".h5ad":
            raise SystemExit(
                "Use INPUT_H5AD for AnnData .h5ad input. "
                f"INPUT_MATRIX received a .h5ad path: {chosen_path}."
            )
        if input_format == "h5ad":
            raise SystemExit("Use INPUT_H5AD for .h5ad input. INPUT_MATRIX cannot be combined with INPUT_FORMAT=h5ad.")
        if input_format == "auto" and not detected_format:
            raise SystemExit(
                "Could not determine INPUT_FORMAT for INPUT_MATRIX automatically. "
                f"Path: {chosen_path}. Set INPUT_FORMAT to one of: {SUPPORTED_MATRIX_INPUT_FORMAT_HELP}."
            )

    resolved_input_format = input_format if input_format != "auto" else detected_format
    if resolved_input_format in {"h5ad", "10x_h5"} and chosen_path.is_dir():
        raise SystemExit(
            f"{chosen_name} points to a directory, but INPUT_FORMAT={resolved_input_format} expects a file path. "
            f"Received: {chosen_path}."
        )
    if resolved_input_format in {"10x_mtx", "parsebio", "scalebio", "cellranger_per_sample_outs"} and not chosen_path.is_dir():
        raise SystemExit(
            f"{chosen_name} points to a file, but INPUT_FORMAT={resolved_input_format} expects a directory. "
            f"Received: {chosen_path}."
        )

    organism = params["organism"].strip().lower()
    if not organism:
        raise SystemExit(
            "Set ORGANISM to a supported alias for QC gene annotation before running scrna_prep. "
            f"Supported values: {SUPPORTED_ORGANISM_HELP}."
        )
    if organism not in SUPPORTED_ORGANISM_ALIASES:
        raise SystemExit(
            "Set ORGANISM to a supported alias for QC gene annotation before running scrna_prep. "
            f"Supported values: {SUPPORTED_ORGANISM_HELP}. Received: {params['organism'].strip()}."
        )
    sample_metadata = params["sample_metadata"].strip()
    if sample_metadata:
        sample_metadata_path = resolve_runtime_path(sample_metadata)
        if not sample_metadata_path.exists():
            raise SystemExit(
                "SAMPLE_METADATA does not exist. Set SAMPLE_METADATA to a CSV file path or leave it empty "
                f"to use assets/samples.csv. Missing path: {sample_metadata_path}."
            )
        if sample_metadata_path.is_dir():
            raise SystemExit(
                "Set SAMPLE_METADATA to a CSV file path, not a directory. "
                f"Received directory: {sample_metadata_path.resolve()}."
            )
    if doublet_method not in SUPPORTED_DOUBLET_METHODS:
        raise SystemExit(
            f"Set DOUBLET_METHOD to one of: {', '.join(SUPPORTED_DOUBLET_METHODS)}. Received: {params['doublet_method'].strip() or '<empty>'}."
        )
    if parse_bool(params["filter_predicted_doublets"]) and doublet_method != "scrublet":
        raise SystemExit(
            "FILTER_PREDICTED_DOUBLETS requires DOUBLET_METHOD=scrublet so predicted doublets are available."
        )
    if qc_mode not in SUPPORTED_QC_MODES:
        raise SystemExit(f"Set QC_MODE to one of: {', '.join(SUPPORTED_QC_MODES)}. Received: {params['qc_mode'].strip() or '<empty>'}.")

    require_float("QC_NMADS", params["qc_nmads"], minimum=0.1)
    require_int("MIN_GENES", params["min_genes"], minimum=0)
    require_int("MIN_CELLS", params["min_cells"], minimum=1)
    require_int("MIN_COUNTS", params["min_counts"], minimum=0)
    require_float("MAX_PCT_COUNTS_MT", params["max_pct_counts_mt"], minimum=0.0, maximum=100.0)
    require_optional_percent("MAX_PCT_COUNTS_RIBO", params["max_pct_counts_ribo"])
    require_optional_percent("MAX_PCT_COUNTS_HB", params["max_pct_counts_hb"])
    require_int("N_TOP_HVGS", params["n_top_hvgs"], minimum=1)
    require_int("N_PCS", params["n_pcs"], minimum=1)
    require_int("N_NEIGHBORS", params["n_neighbors"], minimum=1)
    if params["leiden_resolution"].strip():
        require_float("LEIDEN_RESOLUTION", params["leiden_resolution"], minimum=0.000001)
    for part in str(params["resolution_grid"]).split(","):
        if not part.strip():
            continue
        require_float("RESOLUTION_GRID", part.strip(), minimum=0.000001)


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and optionally run the scrna_prep workspace.")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate inputs and write runtime config files without running pixi or Quarto.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    params = resolved_params()
    validate_params(params)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    project_name = PROJECT_DIR.name
    sample_metadata = params["sample_metadata"].strip() or "assets/samples.csv"

    write_project_config(PROJECT_CONFIG_PATH, params, project_name=project_name, sample_metadata=sample_metadata)
    write_run_info(RUN_INFO_PATH, params, project_name=project_name, sample_metadata=sample_metadata)

    if args.prepare_only:
        return 0

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
