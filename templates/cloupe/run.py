#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import anndata as ad


TEMPLATE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = TEMPLATE_DIR / "config"
DEFAULT_BARCODE_WHITELIST_URL = (
    "https://raw.githubusercontent.com/10XGenomics/supernova/master/"
    "tenkit/lib/python/tenkit/barcodes/737K-august-2016.txt"
)
LOUPE_MAX_CATEGORIES = 32768
DEFAULT_OBS_KEYS = [
    "sample_id",
    "leiden",
    "scrna_annotate_manual_markers_label",
    "scrna_annotate_manual_markers_confidence",
    "scrna_annotate_manual_markers_review_status",
    "scrna_annotate_manual_markers_n_candidates",
    "scrna_annotate_manual_markers_top_score",
    "scrna_annotate_manual_markers_score_margin",
    "scrna_annotate_manual_markers_matched_genes",
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
    params = load_params(parse_args())
    try:
        import anndata as ad
    except ImportError as exc:
        raise SystemExit(
            "[cloupe] anndata is required for conversion; run this script through the template Pixi environment."
        ) from exc
    warnings: list[str] = []
    errors: list[str] = []

    input_h5ad = resolve_input(params)
    output_path = resolve_output(params, input_h5ad)
    metadata_path = resolve_metadata_path(params, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
        obs_keys = prepare_barcodes_for_loupe(adata, params, obs_keys, warnings)
        obs_keys = prepare_obs_for_loupe(adata, obs_keys, warnings)

        write_cloupe(adata, output_path, embedding_key, obs_keys, loupe_layer)
        require_output_file(output_path)
        state = "completed_with_warnings" if warnings else "completed"
    except (Exception, SystemExit) as exc:
        state = "failed"
        errors.append(str(exc))
        write_metadata(
            output_path=output_path,
            metadata_path=metadata_path,
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
        metadata_path=metadata_path,
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert an H5AD object to a Loupe Browser .cloupe file.")
    parser.add_argument("input", nargs="?", help="Input H5AD file. Overrides config when provided.")
    parser.add_argument("--input", dest="input_option", help="Input H5AD file. Alias for the positional input.")
    parser.add_argument("-o", "--output", help="Output .cloupe path. Defaults to next to the input H5AD.")
    parser.add_argument("--counts-layer", help="AnnData layer used as Loupe count matrix. Use X only when X is count-like.")
    parser.add_argument("--embedding-key", help="AnnData obsm key used as the Loupe embedding.")
    parser.add_argument("--obs-keys", help="Comma-separated additional adata.obs columns to export.")
    parser.add_argument(
        "--barcode-mode",
        choices=["original", "synthetic_10x"],
        help="Use original obs names or synthetic 10x-compatible barcodes for Loupe export.",
    )
    parser.add_argument("--barcode-whitelist", help="Local path or URL with 10x-compatible barcodes, one per line.")
    parser.add_argument("--original-barcode-key", help="Loupe metadata column used to store original cell IDs.")
    parser.add_argument("--synthetic-barcode-key", help="Loupe metadata column used to store synthetic barcodes.")
    parser.add_argument("--metadata", help="Metadata JSON output path. Defaults next to the .cloupe file.")
    return parser.parse_args(argv)


def load_params(args: argparse.Namespace) -> dict[str, Any]:
    config = read_toml(CONFIG_DIR / "export.toml")
    input_cfg = dict(config.get("input", {}))
    export_cfg = dict(config.get("export", {}))
    params = {
        "input": input_cfg.get("h5ad", ""),
        "input_h5ad": input_cfg.get("h5ad", ""),
        "output_cloupe": export_cfg.get("output_cloupe", ""),
        "metadata_json": export_cfg.get("metadata_json", ""),
        "counts_layer": export_cfg.get("counts_layer", "counts"),
        "embedding_key": export_cfg.get("embedding_key", "X_umap"),
        "obs_keys": export_cfg.get("obs_keys", ""),
        "barcode_mode": export_cfg.get("barcode_mode", "original"),
        "barcode_whitelist": export_cfg.get("barcode_whitelist", ""),
        "original_barcode_key": export_cfg.get("original_barcode_key", "original_cell_id"),
        "synthetic_barcode_key": export_cfg.get("synthetic_barcode_key", "loupe_synthetic_barcode"),
    }
    overrides = {
        "input": env("INPUT"),
        "input_h5ad": env("INPUT_H5AD"),
        "output_cloupe": env("OUTPUT_CLOUPE"),
        "metadata_json": env("METADATA_JSON"),
        "counts_layer": env("COUNTS_LAYER"),
        "embedding_key": env("EMBEDDING_KEY"),
        "obs_keys": env("OBS_KEYS"),
        "barcode_mode": env("BARCODE_MODE"),
        "barcode_whitelist": env("BARCODE_WHITELIST"),
        "original_barcode_key": env("ORIGINAL_BARCODE_KEY"),
        "synthetic_barcode_key": env("SYNTHETIC_BARCODE_KEY"),
    }
    for key, value in overrides.items():
        if value not in {"", None}:
            params[key] = value
    cli_input = args.input_option or args.input
    arg_overrides = {
        "input": cli_input,
        "input_h5ad": cli_input,
        "output_cloupe": args.output,
        "metadata_json": args.metadata,
        "counts_layer": args.counts_layer,
        "embedding_key": args.embedding_key,
        "obs_keys": args.obs_keys,
        "barcode_mode": args.barcode_mode,
        "barcode_whitelist": args.barcode_whitelist,
        "original_barcode_key": args.original_barcode_key,
        "synthetic_barcode_key": args.synthetic_barcode_key,
    }
    for key, value in arg_overrides.items():
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


def resolve_output(params: dict[str, Any], input_h5ad: Path) -> Path:
    value = str(params.get("output_cloupe") or "").strip()
    if not value:
        value = str(input_h5ad.with_suffix(".cloupe"))
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if path.suffix.lower() != ".cloupe":
        raise SystemExit(f"output must be a .cloupe file: {path}")
    return path


def resolve_metadata_path(params: dict[str, Any], output_path: Path) -> Path:
    value = str(params.get("metadata_json") or "").strip()
    if not value:
        return output_path.with_name(f"{output_path.stem}_export.json")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
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
    if not requested_keys or "*" in requested_keys:
        return list(adata.obs.columns)
    keys: list[str] = []
    for key in DEFAULT_OBS_KEYS + requested_keys:
        if key in adata.obs and key not in keys:
            keys.append(key)
    return keys


def prepare_obs_for_loupe(adata: ad.AnnData, obs_keys: list[str], warnings: list[str]) -> list[str]:
    export_keys: list[str] = []
    for key in obs_keys:
        if key not in adata.obs:
            continue
        values = adata.obs[key].astype("string").fillna("NA")
        n_categories = int(values.nunique(dropna=False))
        if n_categories > LOUPE_MAX_CATEGORIES:
            warnings.append(
                f"Skipped obs column {key!r}: {n_categories} categories exceeds Loupe limit "
                f"of {LOUPE_MAX_CATEGORIES}."
            )
            continue
        adata.obs[key] = values.astype("category")
        export_keys.append(key)
    return export_keys


def prepare_barcodes_for_loupe(
    adata: ad.AnnData,
    params: dict[str, Any],
    obs_keys: list[str],
    warnings: list[str],
) -> list[str]:
    mode = str(params.get("barcode_mode") or "original").strip().lower().replace("-", "_")
    if mode == "original":
        return obs_keys
    if mode != "synthetic_10x":
        raise SystemExit("barcode_mode must be 'original' or 'synthetic_10x'")

    original_key = str(params.get("original_barcode_key") or "original_cell_id").strip()
    synthetic_key = str(params.get("synthetic_barcode_key") or "loupe_synthetic_barcode").strip()
    if not original_key or not synthetic_key:
        raise SystemExit("original_barcode_key and synthetic_barcode_key must not be empty")
    if original_key == synthetic_key:
        raise SystemExit("original_barcode_key and synthetic_barcode_key must be different")

    original_ids = adata.obs_names.astype(str).tolist()
    synthetic_ids = load_synthetic_barcodes(adata.n_obs, str(params.get("barcode_whitelist") or "").strip())
    adata.obs[original_key] = original_ids
    adata.obs[synthetic_key] = synthetic_ids
    maybe_add_sample_from_prefixed_barcodes(adata, original_ids, obs_keys)
    adata.obs_names = synthetic_ids
    warnings.append(
        "Replaced AnnData obs_names with synthetic 10x-compatible barcodes for Loupe export only. "
        f"Original cell IDs are stored in adata.obs[{original_key!r}] in the exported Loupe metadata."
    )
    progress(f"barcode mode: synthetic_10x ({adata.n_obs} export-only barcodes)")
    for key in [original_key, synthetic_key, "pipseq_sample"]:
        if key in adata.obs and key not in obs_keys:
            obs_keys.append(key)
    return obs_keys


def maybe_add_sample_from_prefixed_barcodes(adata: ad.AnnData, original_ids: list[str], obs_keys: list[str]) -> None:
    if "pipseq_sample" in adata.obs or not original_ids:
        return
    if not all(":" in value for value in original_ids):
        return
    samples = [value.split(":", 1)[0] for value in original_ids]
    if len(set(samples)) > 1 or samples[0]:
        adata.obs["pipseq_sample"] = samples
        if "pipseq_sample" not in obs_keys:
            obs_keys.append("pipseq_sample")


def load_synthetic_barcodes(n_obs: int, source: str) -> list[str]:
    source = source or DEFAULT_BARCODE_WHITELIST_URL
    barcodes: list[str] = []
    if source.startswith(("http://", "https://")):
        progress(f"loading synthetic barcode whitelist from URL: {source}")
        with urllib.request.urlopen(source, timeout=60) as handle:
            for raw in handle:
                value = raw.decode("utf-8").strip()
                if value:
                    barcodes.append(value)
                if len(barcodes) >= n_obs:
                    break
    else:
        path = Path(source).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        progress(f"loading synthetic barcode whitelist from file: {path}")
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                value = line.strip()
                if value:
                    barcodes.append(value)
                if len(barcodes) >= n_obs:
                    break
    if len(barcodes) < n_obs:
        raise SystemExit(f"barcode whitelist provided {len(barcodes)} barcodes, but {n_obs} cells need export barcodes")
    if len(set(barcodes)) != len(barcodes):
        raise SystemExit("barcode whitelist contains duplicate barcodes in the selected prefix")
    return barcodes


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


def require_output_file(output_path: Path) -> None:
    if not output_path.exists():
        raise SystemExit(
            f"Loupe export did not create the expected file: {output_path}. "
            "Check converter warnings above; non-10x or otherwise unrecognized cell barcodes can make "
            "the 10x Loupe converter exit without LoupePy raising an exception."
        )
    if output_path.stat().st_size == 0:
        raise SystemExit(f"Loupe export created an empty file: {output_path}")


def write_metadata(
    *,
    output_path: Path,
    metadata_path: Path,
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
            "barcode_mode": params.get("barcode_mode", "original"),
            "barcode_whitelist": params.get("barcode_whitelist", ""),
            "original_barcode_key": params.get("original_barcode_key", "original_cell_id"),
            "synthetic_barcode_key": params.get("synthetic_barcode_key", "loupe_synthetic_barcode"),
        },
        "output": {
            "cloupe": str(output_path),
            "metadata_json": str(metadata_path),
        },
        "status": {
            "state": state,
            "warnings": warnings,
            "errors": errors,
            "started_at": started_at,
            "completed_at": utc_now(),
        },
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("w", encoding="utf-8") as handle:
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
