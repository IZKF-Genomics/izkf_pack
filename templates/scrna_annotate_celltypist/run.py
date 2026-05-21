#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = Path(os.environ.get("LINKAR_PROJECT_DIR", TEMPLATE_DIR.parent)).resolve()
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
TABLES_DIR = RESULTS_DIR / "tables"
CONFIG_DIR = TEMPLATE_DIR / "config"
ANNOTATED_H5AD = RESULTS_DIR / "adata.annotated.h5ad"
SCHEMA_VERSION = "izkf_annotation_result.v1"
TEMPLATE_NAME = "scrna_annotate_celltypist"

PREDICTION_FIELDS = [
    "cell_id",
    "cluster_id",
    "sample_id",
    "predicted_label",
    "majority_label",
    "top_label",
    "confidence_bucket",
    "top_probability",
    "top_score",
]
SUMMARY_FIELDS = ["label", "n_cells", "fraction_cells"]
CLUSTER_FIELDS = ["cluster_id", "n_cells", "top_label", "confidence_bucket", "n_labels", "label_counts", "review_status"]
MODEL_FIELDS = ["model", "description", "inferred_species", "score", "selected"]


def main() -> int:
    started_at = utc_now()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    params = load_params()
    warnings: list[str] = []
    errors: list[str] = []
    artifacts: dict[str, Any] = {
        "report_html": "results/report.html",
        "report_qmd": "results/report.qmd",
        "tables": [
            "results/tables/celltypist_available_models.csv",
            "results/tables/celltypist_predictions.csv",
            "results/tables/celltypist_label_summary.csv",
            "results/tables/celltypist_cluster_summary.csv",
        ],
    }

    input_h5ad = resolve_input_h5ad(params)
    if not input_h5ad.exists():
        raise SystemExit(f"Input h5ad not found: {input_h5ad}")

    organism = normalize_species(params["organism"])
    organism_id = params.get("organism_id") or default_organism_id(organism)
    model_name, model_path, model_species, model_description, available_rows, converted = resolve_model(params, organism, warnings)
    write_csv(TABLES_DIR / "celltypist_available_models.csv", available_rows, MODEL_FIELDS)

    progress(f"reading {input_h5ad}")
    import anndata as ad

    adata = ad.read_h5ad(input_h5ad)
    query = prepare_query_adata(adata, params, warnings)
    cluster_key = params.get("cluster_key") or ""
    sample_key = params.get("sample_key") or ""

    progress(f"running CellTypist with model {model_name}")
    import celltypist

    over_clustering = cluster_key if bool_param(params["majority_voting"]) and cluster_key in query.obs else None
    result = celltypist.annotate(
        query,
        model=str(model_path),
        mode=params["mode"],
        p_thres=float(params["p_thres"]),
        majority_voting=bool_param(params["majority_voting"]),
        over_clustering=over_clustering,
        min_prop=float(params["min_prop"]),
    )

    prediction_rows = prediction_rows_from_result(result, query, cluster_key=cluster_key, sample_key=sample_key, top_n=int(params["top_n_candidates"]))
    label_summary = label_summary_rows(prediction_rows)
    cluster_summary = cluster_summary_rows(prediction_rows) if cluster_key in query.obs else []
    cluster_predictions = cluster_predictions_from_summary(cluster_summary)
    cell_predictions = cell_predictions_from_rows(prediction_rows, result, top_n=int(params["top_n_candidates"]))

    write_csv(TABLES_DIR / "celltypist_predictions.csv", prediction_rows, PREDICTION_FIELDS)
    write_csv(TABLES_DIR / "celltypist_label_summary.csv", label_summary, SUMMARY_FIELDS)
    write_csv(TABLES_DIR / "celltypist_cluster_summary.csv", cluster_summary, CLUSTER_FIELDS)

    if bool_param(params["write_h5ad"]):
        write_annotated_h5ad(
            input_h5ad=input_h5ad,
            output_h5ad=ANNOTATED_H5AD,
            prediction_rows=prediction_rows,
            params=params,
        )
        artifacts["annotated_h5ad"] = "results/adata.annotated.h5ad"

    if converted:
        warnings.append(
            f"CellTypist model '{model_name}' was converted from {model_species} to {organism} with the built-in human/mouse ortholog mapping; review labels with organism- and tissue-specific markers."
        )
    if bool_param(params["majority_voting"]) and over_clustering is None:
        warnings.append("majority_voting was requested, but cluster_key was not present in adata.obs; CellTypist used its own over-clustering heuristic.")

    state = "failed" if errors else "completed_with_warnings" if warnings else "completed"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "template": {"name": TEMPLATE_NAME, "version": "0.1.0"},
        "run": {
            "state": state,
            "warnings": warnings,
            "errors": errors,
            "started_at": started_at,
            "completed_at": utc_now(),
        },
        "input": {
            "h5ad": str(input_h5ad),
            "input_source_template": params.get("input_source_template") or None,
            "organism": organism,
            "organism_id": organism_id,
            "tissue": params.get("tissue") or None,
            "cluster_key": cluster_key or None,
            "sample_key": sample_key or None,
            "expression_layer": params["expression_layer"],
        },
        "method": {
            "name": "CellTypist",
            "annotation_level": "cell",
            "parameters": {
                "model": model_name,
                "model_species": model_species,
                "query_species": organism,
                "converted_model": converted,
                "convert_model": params["convert_model"],
                "ortholog_unique_only": bool_param(params["ortholog_unique_only"]),
                "ortholog_collapse": params["ortholog_collapse"],
                "majority_voting": bool_param(params["majority_voting"]),
                "mode": params["mode"],
                "p_thres": float(params["p_thres"]),
                "min_prop": float(params["min_prop"]),
            },
        },
        "methods": [
            {
                "step": "CellTypist model discovery",
                "tool": "celltypist.models.models_description / get_models_index / download_models",
                "parameters": {
                    "model": params["model"],
                    "force_update_models": bool_param(params["force_update_models"]),
                    "tissue": params.get("tissue") or None,
                    "organism": organism,
                },
            },
            {
                "step": "CellTypist annotation",
                "tool": "celltypist.annotate",
                "parameters": {
                    "majority_voting": bool_param(params["majority_voting"]),
                    "over_clustering": over_clustering,
                    "mode": params["mode"],
                },
            },
        ],
        "resources": [
            {
                "role": "celltypist_model",
                "id": model_name,
                "path": str(model_path),
                "sha256": sha256_file(model_path) if model_path.exists() else "",
                "species": model_species,
                "description": model_description,
                "converted_to_query_species": converted,
            }
        ],
        "cluster_predictions": cluster_predictions,
        "cell_predictions": cell_predictions,
        "artifacts": artifacts,
    }
    write_json(RESULTS_DIR / "annotation_result.json", payload)
    render_report()
    payload["run"]["completed_at"] = utc_now()
    write_json(RESULTS_DIR / "annotation_result.json", payload)
    progress(f"done: {RESULTS_DIR / 'report.html'}")
    return 0


def load_params() -> dict[str, Any]:
    config = read_toml(CONFIG_DIR / "dataset.toml")
    dataset = dict(config.get("dataset", {}))
    celltypist_cfg = dict(config.get("celltypist", {}))
    outputs = dict(config.get("outputs", {}))
    params = {
        "input_h5ad": dataset.get("input_h5ad", ""),
        "input_source_template": dataset.get("input_source_template", ""),
        "organism": dataset.get("organism", "mouse"),
        "organism_id": dataset.get("organism_id", ""),
        "tissue": dataset.get("tissue", ""),
        "cluster_key": dataset.get("cluster_key", "leiden"),
        "sample_key": dataset.get("sample_key", "sample_id"),
        "expression_layer": dataset.get("expression_layer", "X"),
        "model": celltypist_cfg.get("model", "auto"),
        "model_species": celltypist_cfg.get("model_species", "auto"),
        "force_update_models": celltypist_cfg.get("force_update_models", True),
        "convert_model": celltypist_cfg.get("convert_model", "auto"),
        "ortholog_unique_only": celltypist_cfg.get("ortholog_unique_only", True),
        "ortholog_collapse": celltypist_cfg.get("ortholog_collapse", "average"),
        "majority_voting": celltypist_cfg.get("majority_voting", True),
        "mode": celltypist_cfg.get("mode", "best match"),
        "p_thres": celltypist_cfg.get("p_thres", 0.5),
        "min_prop": celltypist_cfg.get("min_prop", 0.0),
        "top_n_candidates": celltypist_cfg.get("top_n_candidates", 3),
        "write_h5ad": outputs.get("write_h5ad", True),
    }
    env_map = {
        "INPUT_H5AD": "input_h5ad",
        "INPUT_SOURCE_TEMPLATE": "input_source_template",
        "ORGANISM": "organism",
        "ORGANISM_ID": "organism_id",
        "TISSUE": "tissue",
        "CLUSTER_KEY": "cluster_key",
        "SAMPLE_ID_KEY": "sample_key",
        "EXPRESSION_LAYER": "expression_layer",
        "CELLTYPIST_MODEL": "model",
        "MODEL": "model",
        "MODEL_SPECIES": "model_species",
        "FORCE_UPDATE_MODELS": "force_update_models",
        "CONVERT_MODEL": "convert_model",
        "MAJORITY_VOTING": "majority_voting",
        "WRITE_H5AD": "write_h5ad",
    }
    for env_key, param_key in env_map.items():
        if env_key in os.environ:
            params[param_key] = os.environ[env_key]
    return params


def resolve_input_h5ad(params: dict[str, Any]) -> Path:
    configured = str(params.get("input_h5ad") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = [
        ("scrna_prep", "results/adata.prep.h5ad"),
        ("scrna_annotate_manual_markers", "results/adata.annotated.h5ad"),
        ("scrna_annotate_sctype", "results/adata.annotated.h5ad"),
        ("scrna_annotate_zebrafish", "results/adata.annotated.h5ad"),
        ("scrna_integrate", "results/adata.integrated.h5ad"),
    ]
    for template_id, rel_path in candidates:
        candidate = PROJECT_DIR / template_id / rel_path
        if candidate.exists():
            params["input_source_template"] = params.get("input_source_template") or template_id
            progress(f"INPUT_H5AD not set; using {template_id} output: {candidate}")
            return candidate.resolve()
    raise SystemExit("input_h5ad is required; no upstream H5AD output was detected")


def resolve_model(params: dict[str, Any], organism: str, warnings: list[str]) -> tuple[str, Path, str, str, list[dict[str, Any]], bool]:
    from celltypist import models

    model_value = str(params["model"]).strip()
    model_species_param = normalize_species(params.get("model_species", "auto"))
    force_update = bool_param(params["force_update_models"])
    available_rows = available_model_rows(force_update=force_update)
    selected = select_model(model_value, available_rows, organism=organism, tissue=str(params.get("tissue") or ""))
    for row in available_rows:
        row["selected"] = "yes" if row["model"] == selected else ""
    model_path = Path(selected).expanduser()
    if model_path.exists():
        model_name = model_path.name
        description = ""
    else:
        model_name = selected
        models.download_models(force_update=force_update, model=model_name)
        model_path = Path(models.get_model_path(model_name))
        description = next((row.get("description", "") for row in available_rows if row["model"] == model_name), "")
    model_species = model_species_param if model_species_param != "auto" else infer_model_species(model_name, description)
    converted = False
    if model_species not in {"auto", organism}:
        convert_setting = str(params["convert_model"]).strip().lower()
        if {model_species, organism} <= {"human", "mouse"} and convert_setting in {"auto", "true", "yes", "1"}:
            progress(f"converting CellTypist model from {model_species} to {organism}")
            model_obj = models.Model.load(str(model_path))
            model_obj.convert(
                unique_only=bool_param(params["ortholog_unique_only"]),
                collapse=str(params["ortholog_collapse"]),
            )
            converted_path = RESULTS_DIR / f"{model_path.stem}.converted_to_{organism}.pkl"
            model_obj.write(str(converted_path))
            model_path = converted_path
            converted = True
        elif convert_setting in {"false", "no", "0"}:
            warnings.append(f"Using {model_species} CellTypist model on {organism} query data without ortholog conversion.")
        else:
            raise SystemExit(f"Selected model appears to be {model_species}, but query organism is {organism}; set convert_model=true/auto or choose a matching model.")
    if model_species == "auto":
        warnings.append("Could not infer CellTypist model species from model name/description; no species conversion was attempted.")
    return model_name, model_path, model_species, description, available_rows, converted


def available_model_rows(*, force_update: bool) -> list[dict[str, Any]]:
    from celltypist import models

    models.get_models_index(force_update=force_update)
    df = models.models_description()
    rows: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        model = str(row.get("model") or "")
        description = str(row.get("description") or "")
        rows.append(
            {
                "model": model,
                "description": description,
                "inferred_species": infer_model_species(model, description),
                "score": 0,
                "selected": "",
            }
        )
    return rows


def select_model(model_value: str, rows: list[dict[str, Any]], *, organism: str, tissue: str) -> str:
    if model_value and model_value != "auto":
        return model_value
    tissue_terms = tissue_search_terms(tissue)
    best_model = ""
    best_score = -1
    for row in rows:
        text = f"{row['model']} {row['description']}".lower()
        species = row["inferred_species"]
        tissue_match = bool(tissue_terms) and any(term in text for term in tissue_terms)
        cross_species_convertible = {species, organism} <= {"human", "mouse"}
        if tissue_match and species == organism:
            score = 4000
        elif tissue_match and cross_species_convertible:
            score = 3000
        elif species == organism:
            score = 2000
        elif tissue_match:
            score = 1000
        else:
            score = 0
        if "immune" in text:
            score += 5
        row["score"] = score
        if score > best_score:
            best_model = row["model"]
            best_score = score
    if not best_model:
        raise SystemExit("CellTypist model API returned no available models")
    return best_model


def tissue_search_terms(tissue: str) -> list[str]:
    text = str(tissue or "").strip().lower()
    aliases = {
        "heart": ["heart", "cardiac", "myocard"],
        "cardiac": ["heart", "cardiac", "myocard"],
        "myocardium": ["heart", "cardiac", "myocard"],
    }
    return aliases.get(text, [text] if text else [])


def prepare_query_adata(adata: Any, params: dict[str, Any], warnings: list[str]) -> Any:
    query = adata.copy()
    layer = str(params["expression_layer"])
    if layer != "X":
        if layer not in query.layers:
            raise SystemExit(f"expression_layer '{layer}' is not present in adata.layers")
        query.X = query.layers[layer].copy()
    if expression_matrix_looks_raw_counts(query.X, adata=query):
        warnings.append("Expression matrix looks count-like; CellTypist expects normalized/log-transformed gene-symbol expression.")
    return query


def prediction_rows_from_result(result: Any, adata: Any, *, cluster_key: str, sample_key: str, top_n: int) -> list[dict[str, Any]]:
    labels_df = result.predicted_labels.copy()
    labels_df.index = labels_df.index.astype(str)
    probs = result.probability_matrix.copy()
    probs.index = probs.index.astype(str)
    scores = result.decision_matrix.copy()
    scores.index = scores.index.astype(str)
    rows: list[dict[str, Any]] = []
    for cell_id in labels_df.index:
        predicted = get_celltypist_value(labels_df.loc[cell_id], "predicted_labels")
        majority = get_celltypist_value(labels_df.loc[cell_id], "majority_voting")
        top_label = majority or predicted
        prob_row = probs.loc[cell_id]
        score_row = scores.loc[cell_id]
        top_probability = float(prob_row.max()) if len(prob_row) else float("nan")
        top_score = float(score_row.max()) if len(score_row) else float("nan")
        rows.append(
            {
                "cell_id": cell_id,
                "cluster_id": str(adata.obs.loc[cell_id, cluster_key]) if cluster_key in adata.obs else "",
                "sample_id": str(adata.obs.loc[cell_id, sample_key]) if sample_key in adata.obs else "",
                "predicted_label": predicted,
                "majority_label": majority,
                "top_label": top_label,
                "confidence_bucket": confidence_bucket(top_probability),
                "top_probability": round(top_probability, 6),
                "top_score": round(top_score, 6),
            }
        )
    return rows


def cell_predictions_from_rows(rows: list[dict[str, Any]], result: Any, *, top_n: int) -> list[dict[str, Any]]:
    probs = result.probability_matrix.copy()
    probs.index = probs.index.astype(str)
    predictions = []
    for row in rows:
        cell_id = row["cell_id"]
        prob_row = probs.loc[cell_id].sort_values(ascending=False).head(top_n)
        candidates = [
            {
                "label_raw": str(label),
                "label_normalized": str(label),
                "rank": rank,
                "provider_score": float(prob),
                "provider_score_name": "celltypist_probability",
                "confidence_bucket": confidence_bucket(float(prob)) if rank == 1 else None,
                "evidence": {"probability": float(prob)},
            }
            for rank, (label, prob) in enumerate(prob_row.items(), start=1)
        ]
        predictions.append(
            {
                "cell_id": cell_id,
                "cluster_id": row.get("cluster_id") or None,
                "top_label": row.get("top_label") or None,
                "confidence_bucket": row.get("confidence_bucket") or "unknown",
                "candidates": candidates,
            }
        )
    return predictions


def cluster_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("cluster_id"):
            grouped[row["cluster_id"]].append(row)
    summaries = []
    for cluster_id, cluster_rows in sorted(grouped.items(), key=lambda item: item[0]):
        counts = Counter(row.get("top_label") or "unknown" for row in cluster_rows)
        top_label, top_n = counts.most_common(1)[0]
        fraction = top_n / len(cluster_rows)
        summaries.append(
            {
                "cluster_id": cluster_id,
                "n_cells": len(cluster_rows),
                "top_label": top_label,
                "confidence_bucket": confidence_bucket(fraction),
                "n_labels": len(counts),
                "label_counts": "; ".join(f"{label}:{count}" for label, count in counts.most_common()),
                "review_status": "review candidate" if fraction >= 0.5 else "heterogeneous CellTypist labels",
            }
        )
    return summaries


def cluster_predictions_from_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    predictions = []
    for row in rows:
        predictions.append(
            {
                "cluster_id": str(row["cluster_id"]),
                "top_label": row.get("top_label") or None,
                "confidence_bucket": row.get("confidence_bucket") or "unknown",
                "n_cells": int(row.get("n_cells") or 0),
                "review_status": row.get("review_status") or "",
                "candidates": [
                    {
                        "label_raw": row.get("top_label") or "unknown",
                        "label_normalized": row.get("top_label") or "unknown",
                        "rank": 1,
                        "provider_score": None,
                        "provider_score_name": "cluster_majority_fraction",
                        "confidence_bucket": row.get("confidence_bucket") or "unknown",
                        "evidence": {"label_counts": row.get("label_counts") or ""},
                    }
                ],
            }
        )
    return predictions


def label_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row.get("top_label") or "unknown" for row in rows)
    total = sum(counts.values()) or 1
    return [{"label": label, "n_cells": count, "fraction_cells": round(count / total, 6)} for label, count in counts.most_common()]


def write_annotated_h5ad(*, input_h5ad: Path, output_h5ad: Path, prediction_rows: list[dict[str, Any]], params: dict[str, Any]) -> None:
    import anndata as ad
    import pandas as pd

    adata = ad.read_h5ad(input_h5ad)
    pred = {row["cell_id"]: row for row in prediction_rows}
    labels = []
    confidences = []
    predicted_labels = []
    majority_labels = []
    scores = []
    for cell_id in adata.obs_names.astype(str):
        row = pred.get(str(cell_id), {})
        labels.append(row.get("top_label") or "unassigned")
        confidences.append(row.get("confidence_bucket") or "unknown")
        predicted_labels.append(row.get("predicted_label") or "")
        majority_labels.append(row.get("majority_label") or "")
        scores.append(row.get("top_probability") or float("nan"))
    adata.obs["scrna_annotate_celltypist_label"] = pd.Categorical(labels)
    adata.obs["scrna_annotate_celltypist_confidence"] = pd.Categorical(confidences)
    adata.obs["scrna_annotate_celltypist_predicted_label"] = pd.Categorical(predicted_labels)
    adata.obs["scrna_annotate_celltypist_majority_label"] = pd.Categorical(majority_labels)
    adata.obs["scrna_annotate_celltypist_score"] = scores
    adata.uns["scrna_annotate_celltypist"] = {
        "schema_version": SCHEMA_VERSION,
        "label_column": "scrna_annotate_celltypist_label",
        "confidence_column": "scrna_annotate_celltypist_confidence",
    }
    output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(output_h5ad)


def get_celltypist_value(row: Any, preferred: str) -> str:
    if preferred in getattr(row, "index", []):
        value = row[preferred]
        return "" if value is None else str(value)
    if len(row) == 0:
        return ""
    value = row.iloc[0]
    return "" if value is None else str(value)


def infer_model_species(model: str, description: str) -> str:
    text = f"{model} {description}".lower()
    if "mouse" in text or "murine" in text:
        return "mouse"
    if "human" in text or "homo sapiens" in text:
        return "human"
    return "auto"


def normalize_species(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"mus musculus", "mouse", "mice", "ncbitaxon:10090", "10090"}:
        return "mouse"
    if text in {"homo sapiens", "human", "ncbitaxon:9606", "9606"}:
        return "human"
    if text in {"", "auto"}:
        return "auto"
    return text


def default_organism_id(organism: str) -> str:
    return {"mouse": "NCBITaxon:10090", "human": "NCBITaxon:9606"}.get(organism, "")


def confidence_bucket(value: float) -> str:
    try:
        value = float(value)
    except Exception:
        return "unknown"
    if value >= 0.8:
        return "high"
    if value >= 0.5:
        return "medium"
    if value >= 0:
        return "low"
    return "unknown"


def expression_matrix_looks_raw_counts(matrix: Any, *, adata: Any) -> bool:
    if "log1p" in getattr(adata, "uns", {}):
        return False
    try:
        import numpy as np
        from scipy import sparse

        sample = matrix[: min(matrix.shape[0], 500), : min(matrix.shape[1], 500)]
        values = sample.data if sparse.issparse(sample) else np.asarray(sample).ravel()
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values)]
        values = values[values > 0]
        if values.size == 0:
            return False
        integer_fraction = float(np.mean(np.isclose(values, np.round(values))))
        return integer_fraction > 0.98 and float(np.nanmax(values)) > 50
    except Exception:
        return False


def render_report() -> None:
    report_qmd = RESULTS_DIR / "report.qmd"
    shutil.copy2(TEMPLATE_DIR / "report.qmd", report_qmd)
    if shutil.which("quarto") is None:
        progress("Quarto is not available; report.qmd was written but report.html was not rendered")
        return
    subprocess.run(["quarto", "render", str(report_qmd.name), "--to", "html"], cwd=RESULTS_DIR, check=True)


def read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bool_param(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def progress(message: str) -> None:
    print(f"[{TEMPLATE_NAME}] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
