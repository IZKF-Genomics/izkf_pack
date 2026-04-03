#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from export_common import (
    build_export_list,
    derive_export_credentials,
    extract_citations,
    fetch_api_payload,
    generate_methods_markdown,
    load_file_payload,
    mock_metadata_payload,
    normalize_metadata_payload,
    now_utc,
    project_authors,
    resolve_metadata_identifiers,
    save_yaml,
    split_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build export bundle artifacts for the Linkar export template.")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--template-dir", default=".")
    parser.add_argument("--results-dir", default="./results")
    parser.add_argument("--export-engine-backends", default="apache, owncloud, sftp")
    parser.add_argument("--export-expiry-days", type=int, default=30)
    parser.add_argument("--export-username", default="")
    parser.add_argument("--export-password", default="")
    parser.add_argument("--agendo-id", default="")
    parser.add_argument("--flowcell-id", default="")
    parser.add_argument("--metadata-source", default="auto")
    parser.add_argument("--metadata-file", default="")
    parser.add_argument("--metadata-api-url", default="https://genomics.rwth-aachen.de/api")
    parser.add_argument("--metadata-api-endpoint", default="/project-output")
    parser.add_argument("--metadata-api-timeout", type=int, default=20)
    parser.add_argument("--include-methods-in-spec", default="true")
    parser.add_argument("--methods-style", default="full")
    parser.add_argument("--skip-if-spec-exists", action="store_true")
    return parser.parse_args()


def to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    template_dir = Path(args.template_dir).resolve()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    project_file = project_dir / "project.yaml"
    if not project_file.exists():
        raise SystemExit(f"project.yaml not found in {project_dir}")

    spec_path = results_dir / "export_job_spec.json"
    if args.skip_if_spec_exists and spec_path.exists():
        print(f"[info] using existing {spec_path}")
        return 0

    from export_common import load_yaml

    project_data = load_yaml(project_file)
    project_name = str(project_data.get("id") or project_dir.name)
    params = {
        "agendo_id": args.agendo_id,
        "flowcell_id": args.flowcell_id,
        "export_username": args.export_username,
        "export_password": args.export_password,
    }
    identifiers = resolve_metadata_identifiers(params, project_data)
    username, password = derive_export_credentials(project_name, params)

    metadata_context = {
        "metadata_identifiers": {
            "agendo_id": identifiers.get("agendo_id") or None,
            "flowcell_id": identifiers.get("flowcell_id") or None,
            "sources": identifiers.get("sources") or {},
        },
        "project_name": project_name,
        "generated_at": now_utc(),
    }
    save_yaml(results_dir / "metadata_context.yaml", metadata_context)

    mode_requested = str(args.metadata_source or "auto").strip().lower()
    mode_used = mode_requested
    fetch_error = ""
    raw_payload: dict[str, object] = {}
    try:
        if mode_requested == "none":
            raw_payload = {}
        elif mode_requested == "file":
            metadata_file = Path(args.metadata_file).expanduser()
            if not metadata_file.is_absolute():
                metadata_file = (project_dir / metadata_file).resolve()
            raw_payload = load_file_payload(metadata_file)
        elif mode_requested == "mock":
            raw_payload = mock_metadata_payload(identifiers)
        elif mode_requested == "api":
            raw_payload = fetch_api_payload(
                args.metadata_api_url,
                args.metadata_api_endpoint,
                identifiers,
                args.metadata_api_timeout,
            )
        else:
            if args.metadata_file:
                metadata_file = Path(args.metadata_file).expanduser()
                if not metadata_file.is_absolute():
                    metadata_file = (project_dir / metadata_file).resolve()
                if metadata_file.exists():
                    mode_used = "file"
                    raw_payload = load_file_payload(metadata_file)
                else:
                    raise FileNotFoundError(f"metadata_file not found in auto mode: {metadata_file}")
            elif identifiers.get("agendo_id") or identifiers.get("flowcell_id"):
                try:
                    mode_used = "api"
                    raw_payload = fetch_api_payload(
                        args.metadata_api_url,
                        args.metadata_api_endpoint,
                        identifiers,
                        args.metadata_api_timeout,
                    )
                except Exception as exc:
                    fetch_error = str(exc)
                    mode_used = "mock"
                    raw_payload = mock_metadata_payload(identifiers)
            else:
                mode_used = "mock"
                raw_payload = mock_metadata_payload(identifiers)
    except Exception as exc:
        fetch_error = str(exc)
        mode_used = "mock"
        raw_payload = mock_metadata_payload(identifiers)

    raw_path = results_dir / "metadata_raw.json"
    raw_path.write_text(json.dumps(raw_payload, indent=2, sort_keys=True), encoding="utf-8")
    normalized = normalize_metadata_payload(raw_payload, identifiers, mode_used)
    normalized_path = results_dir / "metadata_normalized.yaml"
    save_yaml(normalized_path, normalized)
    metadata_context["metadata_fetch"] = {
        "mode_requested": mode_requested,
        "mode_used": mode_used,
        "api_url": args.metadata_api_url,
        "api_endpoint": args.metadata_api_endpoint,
        "metadata_file": args.metadata_file or None,
        "error": fetch_error or None,
        "raw_path": str(raw_path),
        "normalized_path": str(normalized_path),
    }
    save_yaml(results_dir / "metadata_context.yaml", metadata_context)

    export_list = build_export_list(project_dir, project_data, template_dir)
    job_spec = {
        "project_name": project_name,
        "export_list": export_list,
        "backend": split_csv(args.export_engine_backends),
        "username": username,
        "password": password,
        "authors": project_authors(project_data),
        "expiry_days": int(args.export_expiry_days or 0),
        "metadata_identifiers": metadata_context["metadata_identifiers"],
    }
    spec_path.write_text(json.dumps(job_spec, indent=2), encoding="utf-8")

    if to_bool(args.include_methods_in_spec):
        style = str(args.methods_style or "full").strip().lower()
        if style not in {"full", "concise"}:
            style = "full"
        markdown, templates_count, citation_count = generate_methods_markdown(project_dir, style)
        methods_path = results_dir / "project_methods.md"
        methods_path.write_text(markdown, encoding="utf-8")
        methods_context = {
            "style": style,
            "templates_count": templates_count,
            "citation_count": citation_count,
            "full_text": markdown,
            "citations": extract_citations(markdown),
            "protocol_metadata": normalized,
        }
        save_yaml(results_dir / "methods_context.yaml", methods_context)
        raw_spec = json.loads(spec_path.read_text(encoding="utf-8"))
        raw_spec["methods"] = methods_context
        raw_spec["methods_markdown_path"] = str(methods_path)
        spec_path.write_text(json.dumps(raw_spec, indent=2), encoding="utf-8")

    print(f"[info] wrote {spec_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
