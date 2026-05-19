#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from lib.config import load_dataset_params, load_provider_params, resolve_input_h5ad
from lib.dataset import profile_dataset
from lib.io import write_json
from lib.provider_index import write_provider_index
from lib.provider_runner import run_configured_providers


TEMPLATE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = Path(os.environ.get("LINKAR_PROJECT_DIR", TEMPLATE_DIR.parent)).resolve()
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()
CONFIG_DIR = TEMPLATE_DIR / "config"


def progress(message: str) -> None:
    print(f"[scrna_annotate] {message}", flush=True)


def main() -> int:
    progress("loading dataset and provider configuration")
    dataset = load_dataset_params(CONFIG_DIR)
    provider_config = load_provider_params(CONFIG_DIR)
    input_h5ad = resolve_input_h5ad(TEMPLATE_DIR, dataset)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    progress(f"using input h5ad: {input_h5ad}")
    if not dataset.get("tissue"):
        progress("tissue is not set; running exploratory providers in context-light mode")
    if not dataset.get("organism"):
        progress("organism is not set; provider confidence may be limited")

    progress("profiling AnnData input")
    profile = profile_dataset(input_h5ad, dataset)
    write_json(RESULTS_DIR / "dataset_profile.json", profile)
    if profile.get("cluster_count") is not None:
        progress(f"found {profile['cluster_count']} clusters in obs['{dataset.get('cluster_key')}']")

    results = run_configured_providers(
        input_h5ad=input_h5ad,
        dataset=dataset,
        providers=provider_config["providers"],
        template_dir=TEMPLATE_DIR,
        results_dir=RESULTS_DIR,
        progress=progress,
    )

    progress("writing provider index")
    write_provider_index(results, results_dir=RESULTS_DIR, template_dir=TEMPLATE_DIR)
    progress(f"done: {RESULTS_DIR / 'provider_index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
