from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from lib.config import parse_bool
from lib.provider_index import skipped_provider_result
from providers.marker_based.core import run_provider as run_marker_based
from providers.marker_catalog.core import run_provider as run_marker_catalog


ProviderFn = Callable[[Path, dict[str, Any], dict[str, Any]], dict[str, Any]]


def implemented_providers(template_dir: Path, results_dir: Path) -> dict[str, ProviderFn]:
    return {
        "marker_based": lambda input_h5ad, dataset, config: run_marker_based(
            input_h5ad,
            dataset,
            config,
            template_dir=template_dir,
            results_dir=results_dir,
        ),
        "marker_catalog": lambda input_h5ad, dataset, config: run_marker_catalog(
            input_h5ad,
            dataset,
            config,
            template_dir=template_dir,
            results_dir=results_dir,
        ),
    }


def run_configured_providers(
    *,
    input_h5ad: Path,
    dataset: dict[str, Any],
    providers: dict[str, dict[str, Any]],
    template_dir: Path,
    results_dir: Path,
    progress: Callable[[str], None],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    registry = implemented_providers(template_dir, results_dir)

    for provider_id, provider_config in sorted(providers.items()):
        enabled = parse_bool(provider_config.get("enabled", False))
        runner = registry.get(provider_id)
        if not enabled:
            progress(f"provider {provider_id} is disabled")
            results.append(skipped_provider_result(provider_id, provider_config, results_dir))
            continue
        if runner is None:
            progress(f"provider {provider_id} is enabled but not implemented yet")
            results.append(skipped_provider_result(provider_id, provider_config, results_dir))
            continue
        if provider_id == "marker_catalog":
            provider_config = dict(provider_config)
            provider_config["_marker_based_enabled"] = parse_bool(providers.get("marker_based", {}).get("enabled", False))
        progress(f"running provider: {provider_id}")
        payload = runner(input_h5ad, dataset, provider_config)
        state = payload.get("status", {}).get("state", "unknown")
        progress(f"provider {provider_id} finished with state: {state}")
        results.append(payload)

    return results
