#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write runtime inputs for the scverse_scrna_prep template.")
    parser.add_argument("--workspace-dir", default=".")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--results-dir", default="./results")
    parser.add_argument("--input-h5ad", default="")
    parser.add_argument("--input-matrix", default="")
    parser.add_argument("--input-source-template", default="")
    parser.add_argument("--ambient-correction-applied", default="false")
    parser.add_argument("--ambient-correction-method", default="none")
    parser.add_argument("--input-format", default="auto")
    parser.add_argument("--var-names", default="gene_symbols")
    parser.add_argument("--sample-metadata", default="")
    parser.add_argument("--organism", default="")
    parser.add_argument("--batch-key", default="batch")
    parser.add_argument("--condition-key", default="condition")
    parser.add_argument("--sample-id-key", default="sample_id")
    parser.add_argument("--doublet-method", default="none")
    parser.add_argument("--filter-predicted-doublets", default="false")
    parser.add_argument("--qc-mode", default="fixed")
    parser.add_argument("--qc-nmads", default="3.0")
    parser.add_argument("--min-genes", default="200")
    parser.add_argument("--min-cells", default="3")
    parser.add_argument("--min-counts", default="500")
    parser.add_argument("--max-pct-counts-mt", default="20.0")
    parser.add_argument("--max-pct-counts-ribo", default="")
    parser.add_argument("--max-pct-counts-hb", default="")
    parser.add_argument("--n-top-hvgs", default="3000")
    parser.add_argument("--n-pcs", default="30")
    parser.add_argument("--n-neighbors", default="15")
    parser.add_argument("--leiden-resolution", default="")
    parser.add_argument("--resolution-grid", default="0.2,0.4,0.6,0.8,1.0,1.2")
    return parser.parse_args()


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_args(args: argparse.Namespace) -> None:
    if not args.input_h5ad.strip() and not args.input_matrix.strip():
        raise SystemExit("Set either --input-h5ad or --input-matrix before running scverse_scrna_prep.")
    if not args.organism.strip():
        raise SystemExit("Set --organism to a supported value such as human, mouse, hsapiens, or mmusculus.")


def write_project_config(path: Path, args: argparse.Namespace, *, project_name: str, sample_metadata: str) -> None:
    lines = [
        "[project]",
        f"name = {toml_string(project_name)}",
        "",
        "[input]",
        f"input_h5ad = {toml_string(args.input_h5ad)}",
        f"input_matrix = {toml_string(args.input_matrix)}",
        f"input_source_template = {toml_string(args.input_source_template)}",
        f"ambient_correction_applied = {'true' if parse_bool(args.ambient_correction_applied) else 'false'}",
        f"ambient_correction_method = {toml_string(args.ambient_correction_method)}",
        f"input_format = {toml_string(args.input_format)}",
        f"var_names = {toml_string(args.var_names)}",
        f"sample_metadata = {toml_string(sample_metadata)}",
        "",
        "[metadata]",
        f"organism = {toml_string(args.organism)}",
        f"sample_id_key = {toml_string(args.sample_id_key)}",
        f"batch_key = {toml_string(args.batch_key)}",
        f"condition_key = {toml_string(args.condition_key)}",
        "",
        "[qc]",
        f"doublet_method = {toml_string(args.doublet_method)}",
        f"filter_predicted_doublets = {'true' if parse_bool(args.filter_predicted_doublets) else 'false'}",
        f"qc_mode = {toml_string(args.qc_mode)}",
        f"qc_nmads = {args.qc_nmads}",
        f"min_genes = {args.min_genes}",
        f"min_cells = {args.min_cells}",
        f"min_counts = {args.min_counts}",
        f"max_pct_counts_mt = {args.max_pct_counts_mt}",
        f"max_pct_counts_ribo = {toml_string(args.max_pct_counts_ribo)}",
        f"max_pct_counts_hb = {toml_string(args.max_pct_counts_hb)}",
        "",
        "[analysis]",
        f"n_top_hvgs = {args.n_top_hvgs}",
        f"n_pcs = {args.n_pcs}",
        f"n_neighbors = {args.n_neighbors}",
        f"leiden_resolution = {toml_string(args.leiden_resolution)}",
        f"resolution_grid = {toml_string(args.resolution_grid)}",
        "target_sum = 10000",
        "",
        "[output]",
        'adata_file = "results/adata.prep.h5ad"',
        'qc_summary_file = "results/tables/qc_summary.csv"',
        'sample_qc_summary_file = "results/tables/sample_qc_summary.csv"',
        'cluster_counts_file = "results/tables/cluster_counts.csv"',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_run_info(path: Path, args: argparse.Namespace, *, workspace_dir: Path, project_dir: Path, results_dir: Path, project_name: str, sample_metadata: str) -> None:
    payload = {
        "workspace_dir": str(workspace_dir),
        "project_dir": str(project_dir),
        "results_dir": str(results_dir),
        "params": {
            "project_name": project_name,
            "input_h5ad": args.input_h5ad,
            "input_matrix": args.input_matrix,
            "input_source_template": args.input_source_template,
            "ambient_correction_applied": parse_bool(args.ambient_correction_applied),
            "ambient_correction_method": args.ambient_correction_method,
            "input_format": args.input_format,
            "var_names": args.var_names,
            "sample_metadata": sample_metadata,
            "organism": args.organism,
            "sample_id_key": args.sample_id_key,
            "batch_key": args.batch_key,
            "condition_key": args.condition_key,
            "doublet_method": args.doublet_method,
            "filter_predicted_doublets": parse_bool(args.filter_predicted_doublets),
            "qc_mode": args.qc_mode,
            "qc_nmads": args.qc_nmads,
            "min_genes": args.min_genes,
            "min_cells": args.min_cells,
            "min_counts": args.min_counts,
            "max_pct_counts_mt": args.max_pct_counts_mt,
            "max_pct_counts_ribo": args.max_pct_counts_ribo,
            "max_pct_counts_hb": args.max_pct_counts_hb,
            "n_top_hvgs": args.n_top_hvgs,
            "n_pcs": args.n_pcs,
            "n_neighbors": args.n_neighbors,
            "leiden_resolution": args.leiden_resolution,
            "resolution_grid": args.resolution_grid,
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def main() -> int:
    args = parse_args()
    validate_args(args)
    workspace_dir = Path(args.workspace_dir).resolve()
    project_dir = Path(args.project_dir).resolve()
    results_dir = Path(args.results_dir).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "config").mkdir(parents=True, exist_ok=True)

    project_name = project_dir.name
    sample_metadata = args.sample_metadata.strip() or "config/samples.csv"

    write_project_config(
        workspace_dir / "config" / "project.toml",
        args,
        project_name=project_name,
        sample_metadata=sample_metadata,
    )
    write_run_info(
        results_dir / "run_info.yaml",
        args,
        workspace_dir=workspace_dir,
        project_dir=project_dir,
        results_dir=results_dir,
        project_name=project_name,
        sample_metadata=sample_metadata,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
