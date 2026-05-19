from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.config import PROVIDER_GROUPS, parse_bool
from lib.io import relative_to, utc_now, write_json


def skipped_provider_result(provider_id: str, provider_config: dict[str, Any], results_dir: Path) -> dict[str, Any]:
    provider_dir = results_dir / "providers" / provider_id
    enabled = parse_bool(provider_config.get("enabled", False))
    payload = {
        "schema_version": 1,
        "provider": {"id": provider_id, "name": provider_id, "group": PROVIDER_GROUPS.get(provider_id, "mock")},
        "input": {"h5ad": "", "cluster_key": ""},
        "status": {
            "state": "needs_config" if enabled else "skipped",
            "missing_config": [],
            "warnings": [
                "Provider manifest exists, but execution code has not been implemented yet."
                if enabled
                else "Provider is disabled in config/providers.toml."
            ],
            "errors": [],
        },
        "cluster_predictions": [],
        "cell_predictions": [],
        "artifacts": {"reports": [], "tables": [], "figures": [], "logs": []},
        "enabled": enabled,
    }
    write_json(provider_dir / "annotation_result.json", payload)
    return payload


def write_provider_index(provider_results: list[dict[str, Any]], *, results_dir: Path, template_dir: Path) -> None:
    providers = []
    for payload in provider_results:
        provider = payload.get("provider", {})
        status = payload.get("status", {})
        provider_id = str(provider.get("id") or "unknown")
        providers.append(
            {
                "id": provider_id,
                "name": provider.get("name"),
                "group": provider.get("group"),
                "enabled": payload.get("enabled", status.get("state") != "skipped"),
                "state": status.get("state", "failed"),
                "result": relative_to(results_dir / "providers" / provider_id / "annotation_result.json", template_dir),
                "manifest": relative_to(template_dir / "providers" / provider_id / "provider_manifest.yaml", template_dir),
                "warnings": status.get("warnings", []),
                "errors": status.get("errors", []),
            }
        )
    write_json(
        results_dir / "provider_index.json",
        {
            "schema_version": 1,
            "dataset_profile": relative_to(results_dir / "dataset_profile.json", template_dir),
            "providers": providers,
            "created_at": utc_now(),
        },
    )
