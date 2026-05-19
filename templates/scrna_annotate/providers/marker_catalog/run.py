#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TEMPLATE_DIR))

from lib.config import load_dataset_params, load_provider_params, resolve_input_h5ad  # noqa: E402
from providers.marker_catalog.core import run_provider  # noqa: E402


def main() -> int:
    config_dir = TEMPLATE_DIR / "config"
    dataset = load_dataset_params(config_dir)
    providers = load_provider_params(config_dir)["providers"]
    input_h5ad = resolve_input_h5ad(TEMPLATE_DIR, dataset)
    run_provider(input_h5ad, dataset, providers.get("marker_catalog", {}), template_dir=TEMPLATE_DIR, results_dir=TEMPLATE_DIR / "results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
