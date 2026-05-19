#!/usr/bin/env python3
from __future__ import annotations

import sys
import os
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TEMPLATE_DIR))

from lib.config import load_dataset_params, load_provider_params, resolve_input_h5ad  # noqa: E402
from providers.marker_based.core import run_provider  # noqa: E402

CONFIG_DIR = TEMPLATE_DIR / "config"
RESULTS_DIR = Path(os.environ.get("LINKAR_RESULTS_DIR", TEMPLATE_DIR / "results")).resolve()


def main() -> int:
    dataset = load_dataset_params(CONFIG_DIR)
    provider_config = load_provider_params(CONFIG_DIR)["providers"].get("marker_based", {})
    input_h5ad = resolve_input_h5ad(TEMPLATE_DIR, dataset)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_provider(input_h5ad, dataset, provider_config, template_dir=TEMPLATE_DIR, results_dir=RESULTS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
