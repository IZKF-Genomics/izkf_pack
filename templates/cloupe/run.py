#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anndata as ad


TEMPLATE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = TEMPLATE_DIR / "config"
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
DEFAULT_OBS_KEYS = [
    "sample_id",
    "leiden",
    "scrna_annotate_zebrafish_label",
    "scrna_annotate_zebrafish_confidence",
    "scrna_annotate_zebrafish_review_status",
    "scrna_annotate_zebrafish_treatment",
    "scrna_annotate_zebrafish_genotype",
]


def progress(message: str) -> None:
    print(f"[cloupe] {message}", flush=True)


def main() -> int:
    started_at = utc_now()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    params = load_params()
    warnings: list[str] = []
    errors: list[str] = []

    input_h5ad = resolve_input(params)
    output_path = RESULTS_DIR / "output.cloupe"
    progress(f"input h5ad: {input_h5ad}")
    progress(f"output cloupe: {output_path}")

    try:
        adata = ad.read_h5ad(input_h5ad)
        loupe_layer = validate_counts_layer(adata, str(params["counts_layer"]), warnings)
        embedding_key = str(params["embedding_key"])
        if embedding_key not in adata.obsm:
            raise SystemExit(f"embedding_key {embedding_key!r} was not found in adata.obsm")
        if adata.obsm[embedding_key].shape[1] < 2:
            raise SystemExit(f"embedding_key {embedding_key!r} must contain at least two columns")

        obs_keys = selected_obs_keys(adata, parse_obs_keys(params["obs_keys"]))
        for key in obs_keys:
            adata.obs[key] = adata.obs[key].astype(str).fillna("NA")

        write_cloupe(adata, output_path, embedding_key, obs_keys, loupe_layer)
        state = "completed_with_warnings" if warnings else "completed"
    except Exception as exc:
        state = "failed"
        errors.append(str(exc))
        write_metadata(
            output_path=output_path,
            input_h5ad=input_h5ad,
            params=params,
            obs_keys=[],
            warnings=warnings,
            errors=errors,
            state=state,
            started_at=started_at,
        )
        raise

    write_metadata(
        output_path=output_path,
        input_h5ad=input_h5ad,
        params=params,
        obs_keys=obs_keys,
        warnings=warnings,
        errors=errors,
        state=state,
        started_at=started_at,
    )
    progress("done")
    return 0


def load_params() -> dict[str, Any]:
    config = read_toml(CONFIG_DIR / "export.toml")
    input_cfg = dict(config.get("input", {}))
    export_cfg = dict(config.get("export", {}))
    params = {
        "input": input_cfg.get("h5ad", ""),
        "input_h5ad": input_cfg.get("h5ad", ""),
        "counts_layer": export_cfg.get("counts_layer", "counts"),
        "embedding_key": export_cfg.get("embedding_key", "X_umap"),
        "obs_keys": export_cfg.get("obs_keys", ""),
    }
    overrides = {
        "input": env("INPUT"),
        "input_h5ad": env("INPUT_H5AD"),
        "counts_layer": env("COUNTS_LAYER"),
        "embedding_key": env("EMBEDDING_KEY"),
        "obs_keys": env("OBS_KEYS"),
    }
    for key, value in overrides.items():
        if value not in {"", None}:
            params[key] = value
    if params["input"] and not params["input_h5ad"]:
        params["input_h5ad"] = params["input"]
    return params


def read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def env(name: str) -> str:
    return os.environ.get(name, "")


def resolve_input(params: dict[str, Any]) -> Path:
    value = str(params.get("input") or params.get("input_h5ad") or "").strip()
    if not value:
        raise SystemExit("Set INPUT or INPUT_H5AD to the H5AD file before running cloupe.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (TEMPLATE_DIR / path).resolve()
    if not path.exists():
        raise SystemExit(f"input H5AD does not exist: {path}")
    if path.suffix.lower() != ".h5ad":
        raise SystemExit(f"input must be an .h5ad file: {path}")
    return path


def validate_counts_layer(adata: ad.AnnData, counts_layer: str, warnings: list[str]) -> str | None:
    layer = (counts_layer or "counts").strip()
    if layer == "X":
        warnings.append("Using adata.X for Loupe export. Make sure X contains raw or count-like values.")
        return None
    if layer not in adata.layers:
        raise SystemExit(
            f"counts_layer {layer!r} was not found in adata.layers. "
            "Use COUNTS_LAYER=X only when adata.X is count-like."
        )
    return layer


def parse_obs_keys(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def selected_obs_keys(adata: ad.AnnData, requested_keys: list[str]) -> list[str]:
    keys: list[str] = []
    for key in DEFAULT_OBS_KEYS + requested_keys:
        if key in adata.obs and key not in keys:
            keys.append(key)
    return keys


def write_cloupe(
    adata: ad.AnnData,
    output_path: Path,
    embedding_key: str,
    obs_keys: list[str],
    loupe_layer: str | None,
) -> None:
    try:
        import loupepy
    except ImportError as exc:
        raise SystemExit("loupepy is not installed in this environment. Run `pixi install` first.") from exc

    dims = [embedding_key]
    try:
        loupepy.create_loupe_from_anndata(
            adata,
            str(output_path),
            layer=loupe_layer,
            dims=dims,
            obs_keys=obs_keys,
            force=True,
        )
    except TypeError:
        loupepy.create_loupe_from_anndata(adata, str(output_path), dims=dims, obs_keys=obs_keys)
    except Exception as exc:
        message = str(exc)
        setup_hint = (
            "If this is a Loupe converter setup or EULA issue, review the 10x Genomics terms and run: "
            "`pixi run python -c \"import loupepy; loupepy.setup()\"`"
        )
        raise SystemExit(f"Loupe export failed: {message}\n{setup_hint}") from exc


def write_metadata(
    *,
    output_path: Path,
    input_h5ad: Path,
    params: dict[str, Any],
    obs_keys: list[str],
    warnings: list[str],
    errors: list[str],
    state: str,
    started_at: str,
) -> None:
    payload = {
        "schema_version": 1,
        "template": "cloupe",
        "input": {
            "h5ad": str(input_h5ad),
            "counts_layer": params["counts_layer"],
            "embedding_key": params["embedding_key"],
            "obs_keys": obs_keys,
        },
        "output": {
            "cloupe": str(output_path),
        },
        "status": {
            "state": state,
            "warnings": warnings,
            "errors": errors,
            "started_at": started_at,
            "completed_at": utc_now(),
        },
    }
    with (RESULTS_DIR / "cloupe_export.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[cloupe] error: {exc}", file=sys.stderr)
        raise
