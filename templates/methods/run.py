#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate project-level methods drafts.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--project-dir", default="..")
    parser.add_argument("--style", default="publication")
    parser.add_argument("--metadata-api-url", default="")
    parser.add_argument("--use-llm", default="false")
    parser.add_argument("--llm-config", default="")
    parser.add_argument("--llm-base-url", default="")
    parser.add_argument("--llm-model", default="")
    parser.add_argument("--llm-temperature", type=float, default=0.2)
    return parser.parse_args()


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def load_mapping(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return load_json(path)
    return load_yaml(path)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(token in lowered for token in ("password", "token", "secret", "api_key")):
        return "***redacted***" if value not in ("", None) else value
    return value


def compact_mapping(mapping: dict[str, Any], keys: list[str] | None = None) -> dict[str, Any]:
    if keys is None:
        items = mapping.items()
    else:
        items = ((key, mapping.get(key)) for key in keys if key in mapping)
    out: dict[str, Any] = {}
    for key, value in items:
        if value in ("", None, [], {}):
            continue
        out[key] = redact_value(key, value)
    return out


def project_author_text(project_data: dict[str, Any]) -> str:
    author = project_data.get("author")
    if isinstance(author, dict):
        name = str(author.get("name") or "").strip()
        org = str(author.get("organization") or "").strip()
        if name and org:
            return f"{name}, {org}"
        return name or org
    authors = project_data.get("authors")
    if isinstance(authors, list):
        names = []
        for item in authors:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    names.append(name)
        return ", ".join(names)
    return ""


def resolve_run_dir(project_dir: Path, entry: dict[str, Any]) -> Path | None:
    raw = entry.get("history_path") or entry.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (project_dir / path).resolve()
    return path


def run_display_label(entry: dict[str, Any], catalog_entry: dict[str, Any], run_dir: Path | None) -> str:
    base_label = str(catalog_entry.get("label") or entry.get("id") or "Workflow step").strip()
    params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
    name = str(params.get("name") or "").strip()
    if name:
        return f"{base_label}: {name}"
    if run_dir is not None:
        basename = run_dir.name.strip()
        if basename and basename.lower() != str(entry.get("id") or "").strip().lower():
            return f"{base_label}: {basename}"
    return base_label


def resolve_output_path(project_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (project_dir / path).resolve()
    return path


def normalize_id_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return ""


def resolve_metadata_identifiers(project_data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"agendo_id": "", "flowcell_id": "", "sources": {}}

    templates = project_data.get("templates") or []
    if isinstance(templates, list):
        for entry in reversed(templates):
            if not isinstance(entry, dict):
                continue
            entry_params = entry.get("params") or {}
            if not isinstance(entry_params, dict):
                continue
            template_id = str(entry.get("id") or "unknown")
            if not out["agendo_id"]:
                ag = normalize_id_value(entry_params.get("agendo_id"))
                if ag:
                    out["agendo_id"] = ag
                    out["sources"]["agendo_id"] = f"template_params:{template_id}"
            if not out["flowcell_id"]:
                for key in ("flowcell_id", "flow_cell", "flowcell"):
                    fc = normalize_id_value(entry_params.get(key))
                    if fc:
                        out["flowcell_id"] = fc
                        out["sources"]["flowcell_id"] = f"template_params:{template_id}.{key}"
                        break
            if out["agendo_id"] and out["flowcell_id"]:
                break

    if not out["agendo_id"]:
        ag = normalize_id_value(project_data.get("agendo_id"))
        if ag:
            out["agendo_id"] = ag
            out["sources"]["agendo_id"] = "project_root:agendo_id"
    if not out["flowcell_id"]:
        for key in ("flowcell_id", "flow_cell", "flowcell"):
            fc = normalize_id_value(project_data.get(key))
            if fc:
                out["flowcell_id"] = fc
                out["sources"]["flowcell_id"] = f"project_root:{key}"
                break
    return out


def agendo_cache_root() -> Path:
    linkar_home = normalize_id_value(os.getenv("LINKAR_HOME"))
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "agendo_combinedmetadata"
    return Path.home().resolve() / ".linkar" / "agendo_combinedmetadata"


def build_optional_auth_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    user = normalize_id_value(os.getenv("GF_API_NAME"))
    password = normalize_id_value(os.getenv("GF_API_PASS"))
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return headers


def fetch_combined_project_metadata(agendo_id: str, base_url: str) -> list[dict[str, Any]]:
    request = Request(
        f"{base_url.rstrip('/')}/get/combinedmetadata/agendo/{agendo_id}",
        headers=build_optional_auth_headers(),
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while fetching combined metadata for Agendo request {agendo_id}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error while fetching combined metadata for Agendo request {agendo_id}: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected combined metadata payload for Agendo request {agendo_id}")
    return [item for item in payload if isinstance(item, dict)]


def load_cached_combined_project_metadata(agendo_id: str, base_url: str) -> list[dict[str, Any]]:
    root = agendo_cache_root()
    root.mkdir(parents=True, exist_ok=True)
    cache_file = root / f"{agendo_id}.json"
    if cache_file.exists():
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    payload = fetch_combined_project_metadata(agendo_id, base_url)
    cache_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def extract_crucial_project_metadata(payload: list[dict[str, Any]], identifiers: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return compact_mapping({"agendo_id": identifiers.get("agendo_id"), "flowcell_id": identifiers.get("flowcell_id")})

    first = payload[0] if isinstance(payload[0], dict) else {}
    project_output = first.get("ProjectOutput") if isinstance(first.get("ProjectOutput"), dict) else {}
    run_db = first.get("RunMetadataDB") if isinstance(first.get("RunMetadataDB"), dict) else {}

    metadata = {
        "agendo_id": normalize_id_value(project_output.get("agendo_id") or identifiers.get("agendo_id")),
        "project_ref": normalize_id_value(project_output.get("project") or project_output.get("ref")),
        "application": normalize_id_value(project_output.get("application") or project_output.get("agendo_application")),
        "library_kit": normalize_id_value(project_output.get("library_kit")),
        "index_kit": normalize_id_value(project_output.get("index_kit")),
        "umi": normalize_id_value(project_output.get("umi")),
        "spike_in": normalize_id_value(project_output.get("spike_in")),
        "sequencer": normalize_id_value(project_output.get("sequencer")),
        "instrument": normalize_id_value(run_db.get("instrument")),
        "sequencing_kit": normalize_id_value(project_output.get("sequencing_kit") or run_db.get("seq_kit")),
        "read_type": normalize_id_value(project_output.get("read_type")),
        "cycles_read1": project_output.get("cycles_read1") or run_db.get("read1_cycles"),
        "cycles_index1": project_output.get("cycles_index1") or run_db.get("index1_cycles"),
        "cycles_index2": project_output.get("cycles_index2") or run_db.get("index2_cycles"),
        "cycles_read2": project_output.get("cycles_read2") or run_db.get("read2_cycles"),
        "run_date": normalize_id_value(project_output.get("run_date") or run_db.get("date")),
        "flow_cell": normalize_id_value(project_output.get("flow_cell") or run_db.get("flowcell") or identifiers.get("flowcell_id")),
        "sample_number": project_output.get("sample_number"),
        "operator": normalize_id_value(project_output.get("operator")),
        "provider": normalize_id_value(project_output.get("provider") or project_output.get("created_by_name")),
        "group_name": normalize_id_value(project_output.get("group_") or project_output.get("group_name")),
        "organism": normalize_id_value(project_output.get("organism")),
        "phix_percentage": project_output.get("phix_percentage"),
        "prediction_confidence": first.get("PredictionConfidence"),
        "agendo_link": normalize_id_value(project_output.get("agendo_link")),
        "metadata_source": "agendo_combinedmetadata",
    }
    return compact_mapping(metadata)


def resolve_project_api_metadata(project_data: dict[str, Any], api_base_url: str = "") -> dict[str, Any]:
    identifiers = resolve_metadata_identifiers(project_data)
    agendo_id = normalize_id_value(identifiers.get("agendo_id"))
    base_url = normalize_id_value(api_base_url) or normalize_id_value(os.getenv("GF_API_BASE_COMBINEDMETADATA")) or "https://genomics.rwth-aachen.de/api"
    metadata = {
        "identifiers": compact_mapping(identifiers),
        "api_base_url": base_url,
        "project_metadata": {},
    }
    if not agendo_id:
        metadata["reason"] = "No agendo_id found in project history."
        return metadata
    try:
        payload = load_cached_combined_project_metadata(agendo_id, base_url)
        metadata["project_metadata"] = extract_crucial_project_metadata(payload, identifiers)
        metadata["record_count"] = len(payload)
        metadata["fetched"] = True
    except Exception as exc:
        metadata["reason"] = str(exc)
        metadata["fetched"] = False
    return compact_mapping(metadata)


def format_cycle_token(label: str, value: Any) -> str:
    rendered = normalize_id_value(value)
    if not rendered:
        return ""
    return f"{label} {rendered}"


def collect_project_metadata_bullets(context: dict[str, Any]) -> list[str]:
    project_api = context.get("project_api") if isinstance(context.get("project_api"), dict) else {}
    meta = project_api.get("project_metadata") if isinstance(project_api.get("project_metadata"), dict) else {}
    if not meta:
        return []

    sequencing_platform = " / ".join(
        part for part in [normalize_id_value(meta.get("sequencer")), normalize_id_value(meta.get("instrument"))] if part
    )
    cycle_parts = [
        format_cycle_token("R1", meta.get("cycles_read1")),
        format_cycle_token("I1", meta.get("cycles_index1")),
        format_cycle_token("I2", meta.get("cycles_index2")),
        format_cycle_token("R2", meta.get("cycles_read2")),
    ]
    read_config = normalize_id_value(meta.get("read_type"))
    if any(cycle_parts):
        rendered_cycles = "/".join(part for part in cycle_parts if part)
        read_config = f"{read_config}; {rendered_cycles}" if read_config else rendered_cycles

    items = [
        ("Project reference", normalize_id_value(meta.get("project_ref"))),
        ("Assay", format_publication_value("application", meta.get("application"))),
        ("Library kit", normalize_id_value(meta.get("library_kit"))),
        ("Index kit", normalize_id_value(meta.get("index_kit"))),
        ("Sequencing platform", sequencing_platform),
        ("Sequencing kit", normalize_id_value(meta.get("sequencing_kit"))),
        ("Read configuration", read_config),
        ("UMI chemistry", normalize_id_value(meta.get("umi"))),
        ("Spike-in control", normalize_id_value(meta.get("spike_in"))),
        ("Flow cell", normalize_id_value(meta.get("flow_cell"))),
        ("Run date", normalize_id_value(meta.get("run_date"))),
        ("Samples", normalize_id_value(meta.get("sample_number"))),
        ("PhiX", normalize_id_value(meta.get("phix_percentage")) and f"{meta.get('phix_percentage')}%"),
    ]

    lines: list[str] = []
    seen: set[str] = set()
    for label, value in items:
        if not is_meaningful_value(value):
            continue
        line = f"- {label}: `{value}`"
        if line not in seen:
            lines.append(line)
            seen.add(line)
    return lines


def read_linkar_runtime(run_dir: Path | None) -> dict[str, Any]:
    if run_dir is None:
        return {}
    runtime = load_json(run_dir / ".linkar" / "runtime.json")
    return compact_mapping(
        runtime,
        keys=["command", "cwd", "returncode", "success", "started_at", "finished_at", "duration_seconds"],
    )


def load_runtime_command(project_dir: Path, run_dir: Path | None, outputs: dict[str, Any]) -> dict[str, Any]:
    candidates: list[Path] = []
    explicit = resolve_output_path(project_dir, outputs.get("runtime_command"))
    if explicit is not None:
        candidates.append(explicit)
    if run_dir is not None:
        candidates.append(run_dir / "results" / "runtime_command.json")
    for path in candidates:
        payload = load_json(path)
        if payload:
            payload.setdefault("path", str(path))
            return payload
    return {}


def load_software_versions(project_dir: Path, run_dir: Path | None, outputs: dict[str, Any]) -> list[dict[str, Any]]:
    versions: list[dict[str, Any]] = []
    candidates: list[Path] = []
    software_path = resolve_output_path(project_dir, outputs.get("software_versions"))
    if software_path is not None:
        candidates.append(software_path)
    if run_dir is not None:
        candidates.append(run_dir / "results" / "software_versions.json")
    seen: set[Path] = set()
    for software_path in candidates:
        if software_path in seen or not software_path.exists():
            continue
        seen.add(software_path)
        try:
            raw = json.loads(software_path.read_text(encoding="utf-8"))
            items = raw.get("software") if isinstance(raw, dict) else None
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        versions.append(item)
        except Exception as exc:
            versions.append(
                {
                    "name": "software_versions",
                    "source": "output",
                    "path": str(software_path),
                    "error": str(exc),
                }
            )
    for key, value in outputs.items():
        if not isinstance(key, str) or not key.startswith("version_"):
            continue
        path = resolve_output_path(project_dir, value)
        if path is None or not path.exists():
            continue
        versions.append(
            {
                "name": key.removeprefix("version_").replace("_", "-"),
                "version": path.read_text(encoding="utf-8", errors="replace").strip(),
                "path": str(path),
                "source": "output",
            }
        )
    return versions


def infer_organism_or_reference(params: dict[str, Any]) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    for key in ("organism", "genome", "reference", "spikein"):
        value = params.get(key)
        if value not in ("", None):
            hints[key] = value
    return hints


def summarize_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in outputs.items():
        if isinstance(value, list):
            summary[key] = {"count": len(value), "examples": value[:3]}
        elif value not in ("", None):
            summary[key] = value
    return summary


def explain_params(params: dict[str, Any], explanations: dict[str, Any]) -> list[dict[str, str]]:
    rendered: list[dict[str, str]] = []
    for key, value in params.items():
        detail = explanations.get(key) if isinstance(explanations, dict) else None
        rendered.append(
            {
                "name": key,
                "value": json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else str(value),
                "explanation": str(detail or "").strip(),
            }
        )
    return rendered


def select_catalog_entry(catalog: dict[str, Any], template_id: str) -> dict[str, Any]:
    templates = catalog.get("templates")
    if not isinstance(templates, dict):
        return {}
    entry = templates.get(template_id)
    return entry if isinstance(entry, dict) else {}


def collect_run_context(
    project_dir: Path,
    project_data: dict[str, Any],
    catalog: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    runs: list[dict[str, Any]] = []
    citation_ids: list[str] = []
    for index, entry in enumerate(project_data.get("templates") or [], start=1):
        if not isinstance(entry, dict):
            continue
        template_id = str(entry.get("id") or "").strip()
        if not template_id or template_id in {"export", "methods"}:
            continue
        params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
        outputs = entry.get("outputs") if isinstance(entry.get("outputs"), dict) else {}
        catalog_entry = select_catalog_entry(catalog, template_id)
        important_params = catalog_entry.get("important_params")
        if not isinstance(important_params, list):
            important_params = None
        params_compact = compact_mapping(params, keys=important_params)
        run_dir = resolve_run_dir(project_dir, entry)
        citations = catalog_entry.get("citations") if isinstance(catalog_entry.get("citations"), list) else []
        citation_ids.extend(str(item) for item in citations if str(item).strip())
        runtime_command = load_runtime_command(project_dir, run_dir, outputs)
        runs.append(
            {
                "order": index,
                "template": template_id,
                "version": entry.get("template_version"),
                "instance_id": entry.get("instance_id"),
                "label": run_display_label(entry, catalog_entry, run_dir),
                "category": str(catalog_entry.get("category") or "").strip(),
                "publication_relevance": parse_bool(catalog_entry.get("publication_relevance"), default=True),
                "summary": catalog_entry.get("summary"),
                "catalog": {
                    "method_core": catalog_entry.get("method_core"),
                    "method_details": catalog_entry.get("method_details") if isinstance(catalog_entry.get("method_details"), list) else [],
                    "param_explanations": catalog_entry.get("param_explanations") if isinstance(catalog_entry.get("param_explanations"), dict) else {},
                    "param_context": catalog_entry.get("param_context") if isinstance(catalog_entry.get("param_context"), list) else [],
                    "command_hints": catalog_entry.get("command_hints") if isinstance(catalog_entry.get("command_hints"), list) else [],
                    "tools": catalog_entry.get("tools") if isinstance(catalog_entry.get("tools"), list) else [],
                },
                "params": params_compact,
                "interpreted_params": explain_params(
                    params_compact,
                    catalog_entry.get("param_explanations") if isinstance(catalog_entry.get("param_explanations"), dict) else {},
                ),
                "organism_or_reference": infer_organism_or_reference(params),
                "software_versions": load_software_versions(project_dir, run_dir, outputs),
                "outputs": summarize_outputs(outputs),
                "runtime": read_linkar_runtime(run_dir),
                "runtime_command": runtime_command,
                "citations": citations,
                "run_dir": str(run_dir) if run_dir is not None else "",
            }
        )
    return runs, sorted(set(citation_ids))


def format_param_sentence(params: dict[str, Any]) -> str:
    if not params:
        return ""
    parts = []
    for key, value in params.items():
        rendered = json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else str(value)
        parts.append(f"{key}={rendered}")
    return "; ".join(parts)


def is_meaningful_value(value: Any) -> bool:
    if value in ("", None, [], {}):
        return False
    if isinstance(value, str) and value.strip().lower() in {"none", "null", "na", "n/a"}:
        return False
    return True


def clean_runtime_version(name: str, version: str, raw: str) -> str:
    if version and version != "N E X T F L O W":
        return version
    if name.lower() == "nextflow" and raw:
        match = re.search(r"version\s+([0-9][^\s]*)", raw, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    if raw:
        first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
        return first_line
    return version


def software_display_name(name: str) -> str:
    mapping = {
        "bcl-convert": "BCL Convert",
        "cellranger-atac": "Cell Ranger ATAC",
        "nextflow": "Nextflow",
        "quarto": "Quarto",
        "pixi": "pixi",
    }
    return mapping.get(name.lower(), name)


def format_publication_value(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "enabled" if value else "disabled"
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    text = str(value).strip()
    if key == "application":
        normalized = text.lower().replace("-", "").replace("_", "").replace(" ", "")
        if normalized in {"3mrnaseq", "3mrna", "3mseq"}:
            return "3' mRNA-seq"
    if key == "qc_tool":
        mapping = {"falco": "Falco", "fastqc": "FastQC"}
        return mapping.get(text.lower(), text)
    return text


def merged_run_params(run: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    params = run.get("params") if isinstance(run.get("params"), dict) else {}
    for key, value in params.items():
        if is_meaningful_value(value):
            merged[key] = value
    runtime_command = run.get("runtime_command") if isinstance(run.get("runtime_command"), dict) else {}
    runtime_params = runtime_command.get("params") if isinstance(runtime_command.get("params"), dict) else {}
    for key, value in runtime_params.items():
        if is_meaningful_value(value):
            merged[key] = value
    return merged


def runtime_command_has_flag(run: dict[str, Any], flag: str) -> bool:
    runtime_command = run.get("runtime_command") if isinstance(run.get("runtime_command"), dict) else {}
    command = runtime_command.get("command")
    return isinstance(command, list) and any(str(token) == flag for token in command)


def runtime_command_value_after_flag(run: dict[str, Any], flag: str) -> str:
    runtime_command = run.get("runtime_command") if isinstance(run.get("runtime_command"), dict) else {}
    command = runtime_command.get("command")
    if not isinstance(command, list):
        return ""
    for index, token in enumerate(command):
        if str(token) != flag:
            continue
        if index + 1 < len(command):
            return str(command[index + 1]).strip()
    return ""


def pipeline_phrase(run: dict[str, Any]) -> str:
    runtime_command = run.get("runtime_command") if isinstance(run.get("runtime_command"), dict) else {}
    pipeline = str(runtime_command.get("pipeline") or "").strip()
    version = str(runtime_command.get("pipeline_version") or "").strip()
    if pipeline and version:
        return f"`{pipeline}` (v{version})"
    if pipeline:
        return f"`{pipeline}`"
    return ""


def build_publication_summary(run: dict[str, Any]) -> str:
    template = str(run.get("template") or "").strip()
    pipeline = pipeline_phrase(run)

    if template == "demultiplex":
        outputs = run.get("outputs") if isinstance(run.get("outputs"), dict) else {}
        qc_tool = format_publication_value("qc_tool", merged_run_params(run).get("qc_tool", ""))
        summary = "Raw sequencing output was demultiplexed into sample-specific FASTQ files using Illumina BCL conversion."
        qc_parts = []
        if qc_tool:
            qc_parts.append(f"Read quality was assessed with {qc_tool}")
        if outputs.get("multiqc_report"):
            qc_parts.append("summarized with MultiQC")
        if qc_parts:
            summary += " " + " and ".join(qc_parts) + "."
        return summary

    if template == "nfcore_3mrnaseq":
        if pipeline:
            return (
                "3' mRNA-seq libraries were processed with "
                f"{pipeline} under a facility-specific configuration using Nextflow, "
                "with STAR alignment and Salmon quantification."
            )
        return (
            "3' mRNA-seq libraries were processed under a facility-specific configuration "
            "with STAR alignment and Salmon quantification."
        )

    if template == "dgea":
        return (
            "Differential gene expression analysis was prepared in an editable R/Quarto workspace "
            "configured for downstream DESeq2-based reporting from quantified transcript counts "
            "and sample metadata."
        )

    if template == "ercc":
        return (
            "ERCC spike-in performance was assessed from Salmon quantification results in a "
            "Quarto-rendered quality-control workspace."
        )

    catalog = run.get("catalog") if isinstance(run.get("catalog"), dict) else {}
    method_core = str(catalog.get("method_core") or "").strip()
    if method_core:
        return method_core
    return str(run.get("summary") or "").strip()


def project_metadata(context: dict[str, Any]) -> dict[str, Any]:
    project_api = context.get("project_api") if isinstance(context.get("project_api"), dict) else {}
    return project_api.get("project_metadata") if isinstance(project_api.get("project_metadata"), dict) else {}


def nfcore_project_umi_text(context: dict[str, Any]) -> str:
    return normalize_id_value(project_metadata(context).get("umi"))


def load_text_file(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def parse_nextflow_genome_blocks(config_text: str) -> dict[str, dict[str, str]]:
    blocks: dict[str, dict[str, str]] = {}
    pattern = re.compile(r"'([^']+)'\s*\{(.*?)^\s*\}", flags=re.MULTILINE | re.DOTALL)
    for genome_name, body in pattern.findall(config_text):
        fasta_match = re.search(r"fasta\s*=\s*'([^']+)'", body)
        gtf_match = re.search(r"gtf\s*=\s*'([^']+)'", body)
        blocks[genome_name] = {
            "fasta": fasta_match.group(1).strip() if fasta_match else "",
            "gtf": gtf_match.group(1).strip() if gtf_match else "",
        }
    return blocks


def derive_annotation_version(gtf_path: str) -> str:
    gtf_name = Path(gtf_path).name
    match = re.search(r"gencode\.v([0-9A-Za-z]+)", gtf_name, flags=re.IGNORECASE)
    if match:
        return f"Gencode v{match.group(1)}"
    match = re.search(r"\.([0-9]{2,4})\.gtf(?:\.gz)?$", gtf_name, flags=re.IGNORECASE)
    if match:
        return f"release {match.group(1)}"
    return ""


def collect_reference_detail_bullets(run: dict[str, Any]) -> list[str]:
    template = str(run.get("template") or "").strip()
    if template not in {"nfcore_3mrnaseq", "nfcore_methylseq"}:
        return []

    params = merged_run_params(run)
    runtime_command = run.get("runtime_command") if isinstance(run.get("runtime_command"), dict) else {}
    config_path = normalize_id_value(
        (runtime_command.get("artifacts") if isinstance(runtime_command.get("artifacts"), dict) else {}).get("nextflow_config")
    )
    config_text = load_text_file(config_path)
    genome_blocks = parse_nextflow_genome_blocks(config_text) if config_text else {}

    requested_genome = format_publication_value("genome", params.get("genome") or "")
    effective_genome = format_publication_value("genome", params.get("effective_genome") or params.get("genome") or "")
    block = genome_blocks.get(effective_genome) or {}
    fasta_path = normalize_id_value(block.get("fasta"))
    gtf_path = normalize_id_value(block.get("gtf"))
    annotation_version = derive_annotation_version(gtf_path)

    if not annotation_version and effective_genome.endswith("_with_ERCC"):
        base_block = genome_blocks.get(effective_genome.removesuffix("_with_ERCC")) or {}
        annotation_version = derive_annotation_version(normalize_id_value(base_block.get("gtf")))

    items = [
        ("Requested genome", requested_genome),
        ("Effective genome", effective_genome if effective_genome and effective_genome != requested_genome else ""),
        ("Genome FASTA", Path(fasta_path).name if fasta_path else ""),
        ("Annotation file", Path(gtf_path).name if gtf_path else ""),
        ("Annotation version", annotation_version),
    ]
    lines: list[str] = []
    seen: set[str] = set()
    for label, value in items:
        if not is_meaningful_value(value):
            continue
        line = f"- {label}: `{value}`"
        if line not in seen:
            lines.append(line)
            seen.add(line)
    return lines


def collect_command_parameter_bullets(run: dict[str, Any], context: dict[str, Any]) -> list[str]:
    template = str(run.get("template") or "").strip()
    if template not in {"nfcore_3mrnaseq", "nfcore_methylseq"}:
        return []

    runtime_command = run.get("runtime_command") if isinstance(run.get("runtime_command"), dict) else {}
    pipeline_version = normalize_id_value(runtime_command.get("pipeline_version"))
    params = merged_run_params(run)
    items: list[tuple[str, str]] = []

    profile = runtime_command_value_after_flag(run, "-profile")
    if pipeline_version:
        items.append(("Workflow revision", pipeline_version))
    if profile:
        items.append(("Execution profile", profile))

    if template == "nfcore_3mrnaseq":
        genome = format_publication_value("genome", params.get("effective_genome") or params.get("genome") or "")
        if genome:
            items.append(("Command genome", genome))
        if runtime_command_has_flag(run, "--gencode"):
            items.append(("Annotation mode", "Gencode"))
        featurecounts_group = runtime_command_value_after_flag(run, "--featurecounts_group_type")
        if featurecounts_group:
            items.append(("featureCounts grouping", featurecounts_group))
        salmon_args = next(
            (
                str(token).split("=", 1)[1]
                for token in runtime_command.get("command") or []
                if isinstance(token, str) and token.startswith("--extra_salmon_quant_args=")
            ),
            "",
        )
        if salmon_args:
            items.append(("Salmon quant arguments", salmon_args))
        star_args = next(
            (
                str(token).split("=", 1)[1]
                for token in runtime_command.get("command") or []
                if isinstance(token, str) and token.startswith("--extra_star_align_args=")
            ),
            "",
        )
        if star_args:
            items.append(("STAR alignment arguments", star_args))
        umi_project_value = nfcore_project_umi_text(context)
        umi_runtime_value = format_publication_value("umi", params.get("umi") or "")
        if runtime_command_has_flag(run, "--with_umi"):
            items.append(("UMI handling", umi_runtime_value or umi_project_value or "enabled"))
            extract_method = runtime_command_value_after_flag(run, "--umitools_extract_method")
            if extract_method:
                items.append(("UMI extract method", extract_method))
            bc_pattern = runtime_command_value_after_flag(run, "--umitools_bc_pattern")
            if bc_pattern:
                items.append(("UMI barcode pattern", bc_pattern))
        elif umi_project_value:
            items.append(("UMI chemistry", umi_project_value))

    if template == "nfcore_methylseq":
        genome = format_publication_value("genome", params.get("genome") or "")
        if genome:
            items.append(("Command genome", genome))
        if runtime_command_has_flag(run, "--rrbs") or parse_bool(params.get("rrbs"), default=False):
            items.append(("RRBS mode", "enabled"))

    lines: list[str] = []
    seen: set[str] = set()
    for label, value in items:
        if not is_meaningful_value(value):
            continue
        line = f"- {label}: `{value}`"
        if line not in seen:
            lines.append(line)
            seen.add(line)
    return lines


def collect_recorded_command_block(run: dict[str, Any]) -> str:
    template = str(run.get("template") or "").strip()
    if template not in {"nfcore_3mrnaseq", "nfcore_methylseq"}:
        return ""
    runtime_command = run.get("runtime_command") if isinstance(run.get("runtime_command"), dict) else {}
    command_pretty = normalize_id_value(runtime_command.get("command_pretty"))
    if not command_pretty:
        return ""
    return "```bash\n" + command_pretty + "\n```"


def collect_setting_bullets(run: dict[str, Any], context: dict[str, Any]) -> list[str]:
    template = str(run.get("template") or "").strip()
    params = merged_run_params(run)
    items: list[tuple[str, str]] = []

    if template == "nfcore_3mrnaseq":
        reference = format_publication_value("genome", params.get("effective_genome") or params.get("genome") or "")
        spikein = format_publication_value("spikein", params.get("spikein") or "")
        umi_value = format_publication_value("umi", params.get("umi") or "")
        project_umi = nfcore_project_umi_text(context)
        if reference:
            items.append(("Reference genome", reference))
        if spikein:
            items.append(("Spike-in control", spikein))
        if runtime_command_has_flag(run, "--with_umi"):
            items.append(("UMI handling", umi_value or project_umi or "enabled"))
        elif project_umi:
            items.append(("UMI chemistry", project_umi))
    else:
        label_map = {
            "reference": "Reference",
            "run_aggr": "Aggregation",
            "qc_tool": "FASTQ quality control",
            "contamination_tool": "Contamination screening",
            "genome": "Reference genome",
            "effective_genome": "Reference genome",
            "organism": "Organism",
            "spikein": "Spike-in control",
            "application": "Assay context",
        }
        hidden_keys = {
            "authors",
            "author",
            "samplesheet",
            "salmon_dir",
            "name",
            "max_cpus",
            "max_memory",
            "resume",
            "threads",
            "bcl_dir",
            "bracken_db",
            "fastq_screen_conf",
            "flowcell_id",
            "kraken_db",
            "agendo_id",
            "use_api_samplesheet",
        }
        for key, label in label_map.items():
            if key in hidden_keys:
                continue
            value = params.get(key)
            if not is_meaningful_value(value):
                continue
            rendered = format_publication_value(key, value)
            if rendered:
                items.append((label, rendered))

    lines: list[str] = []
    seen: set[str] = set()
    for label, value in items:
        line = f"- {label}: `{value}`"
        if line not in seen:
            lines.append(line)
            seen.add(line)
    return lines


def collect_software_bullets(run: dict[str, Any]) -> list[str]:
    software_versions = run.get("software_versions") if isinstance(run.get("software_versions"), list) else []
    if not software_versions:
        return []

    hidden_names = {"execution_profile", "genome", "spikein", "umi", "application", "organism", "reference", "pixi"}
    lines: list[str] = []
    seen: set[str] = set()
    for item in software_versions:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in hidden_names:
            continue
        version = clean_runtime_version(
            name=name,
            version=str(item.get("version") or "").strip(),
            raw=str(item.get("raw") or "").strip(),
        )
        rendered = f"- `{software_display_name(name)}`"
        if version:
            rendered += f" `{version}`"
        if rendered not in seen:
            lines.append(rendered)
            seen.add(rendered)
    return lines


def collect_method_detail_bullets(run: dict[str, Any]) -> list[str]:
    catalog = run.get("catalog") if isinstance(run.get("catalog"), dict) else {}
    raw_details = catalog.get("method_details") if isinstance(catalog.get("method_details"), list) else []
    template = str(run.get("template") or "").strip()
    params = merged_run_params(run)
    lines: list[str] = []
    seen: set[str] = set()

    for detail in raw_details:
        if not isinstance(detail, str):
            continue
        text = detail.strip()
        if not text:
            continue
        lowered = text.lower()
        if "when ercc spike-ins are present" in lowered and not is_meaningful_value(params.get("spikein")):
            continue
        if "when umi handling is enabled" in lowered and not (
            runtime_command_has_flag(run, "--with_umi") or is_meaningful_value(params.get("umi"))
        ):
            continue
        if text not in seen:
            lines.append(f"- {text}")
            seen.add(text)
    return lines


def collect_reference_bullets(run: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    refs = catalog.get("references") if isinstance(catalog.get("references"), dict) else {}
    citations = run.get("citations") if isinstance(run.get("citations"), list) else []
    lines: list[str] = []
    seen: set[str] = set()
    for citation_id in citations:
        entry = refs.get(str(citation_id)) if isinstance(refs, dict) else None
        if isinstance(entry, dict):
            text = str(entry.get("text") or citation_id).strip()
            url = str(entry.get("url") or "").strip()
            rendered = f"- {text}" + (f" {url}" if url else "")
        else:
            rendered = f"- {citation_id}"
        if rendered not in seen:
            lines.append(rendered)
            seen.add(rendered)
    return lines


def deterministic_long_methods(context: dict[str, Any], catalog: dict[str, Any]) -> str:
    lines = ["# Methods", ""]
    project_metadata = collect_project_metadata_bullets(context)
    if project_metadata:
        lines.append("## Project Assay Metadata")
        lines.append("Project-level sequencing metadata were recovered from the Agendo combined metadata API and used as assay context for the methods narrative.")
        lines.append("")
        lines.extend(project_metadata)
        lines.append("")
    publication_runs = [
        run
        for run in context.get("runs") or []
        if isinstance(run, dict) and parse_bool(run.get("publication_relevance"), default=True)
    ]
    if not publication_runs:
        lines.append("No publication-relevant workflow steps were identified in the recorded project history.")
        return "\n".join(lines).rstrip() + "\n"

    for run in publication_runs:
        if not isinstance(run, dict):
            continue
        label = str(run.get("label") or run.get("template") or "Workflow step")
        lines.append(f"## {label}")
        summary = build_publication_summary(run)
        if summary:
            lines.append(summary)
        details = collect_method_detail_bullets(run)
        if details:
            lines.append("")
            lines.append("### Computational Approach")
            lines.extend(details)
        settings = collect_setting_bullets(run, context)
        if settings:
            lines.append("")
            lines.append("### Relevant Settings")
            lines.extend(settings)
        reference_details = collect_reference_detail_bullets(run)
        if reference_details:
            lines.append("")
            lines.append("### Reference Details")
            lines.extend(reference_details)
        command_parameters = collect_command_parameter_bullets(run, context)
        if command_parameters:
            lines.append("")
            lines.append("### Key Command Parameters")
            lines.extend(command_parameters)
        command_block = collect_recorded_command_block(run)
        if command_block:
            lines.append("")
            lines.append("### Recorded Command")
            lines.append(command_block)
        software = collect_software_bullets(run)
        if software:
            lines.append("")
            lines.append("### Software")
            lines.extend(software)
        references = collect_reference_bullets(run, catalog)
        if references:
            lines.append("")
            lines.append("### References")
            lines.extend(references)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def deterministic_short_methods(context: dict[str, Any]) -> str:
    runs = [
        run
        for run in context.get("runs") or []
        if isinstance(run, dict) and parse_bool(run.get("publication_relevance"), default=True)
    ]
    steps = [str(run.get("label") or run.get("template")) for run in runs]
    project = context.get("project") if isinstance(context.get("project"), dict) else {}
    project_id = str(project.get("id") or "the project")
    text = f"Project `{project_id}` includes {len(runs)} publication-relevant workflow step(s)"
    if steps:
        text += ": " + ", ".join(steps)
    return text + ".\n"


def references_markdown(citation_ids: list[str], catalog: dict[str, Any]) -> str:
    refs = catalog.get("references") if isinstance(catalog.get("references"), dict) else {}
    lines = ["# References", ""]
    if not citation_ids:
        lines.append("No template-level references were selected.")
        return "\n".join(lines) + "\n"
    for citation_id in citation_ids:
        entry = refs.get(citation_id) if isinstance(refs, dict) else None
        if isinstance(entry, dict):
            text = str(entry.get("text") or citation_id)
            url = str(entry.get("url") or "").strip()
            lines.append(f"- {text}" + (f" {url}" if url else ""))
        else:
            lines.append(f"- {citation_id}")
    return "\n".join(lines) + "\n"


def build_prompt(context: dict[str, Any], long_draft: str, short_draft: str, references: str, style: str) -> str:
    return "\n".join(
        [
            "You are helping write publication-ready scientific methods from structured workflow provenance.",
            f"Style: {style}",
            "Use the structured context as the source of truth.",
            "Treat each template catalog entry as template-level scientific guidance.",
            "Treat runtime_command, runtime params, software_versions, and recorded outputs as the run-specific truth for this project.",
            "Treat project_api.project_metadata as project-level assay and sequencing metadata when available.",
            "Runs marked with publication_relevance=false are operational or administrative context and should normally not appear in the final publication methods narrative unless explicitly needed.",
            "Do not mention Linkar, internal template mechanics, recorded authorship metadata, runtime success flags, local file paths, or execution commands unless explicitly requested.",
            "Keep the long methods text readable for scientific users and focused on publication-relevant analytical content.",
            "Use a clear section structure.",
            "For the long methods text, include enough methodological detail to explain the computational approach used in each workflow step.",
            "When project-level assay metadata are available, include the crucial sequencing and library-preparation details in a concise publication-appropriate way.",
            "For pipeline-style workflows such as nf-core runs, include the key recorded command parameters and the best available reference details, including genome and annotation version when recoverable from recorded files.",
            "When multiple settings or parameters are relevant, present them as bullet lists instead of dense prose.",
            "Only mention settings that materially affect the analysis or interpretation.",
            "Include the relevant citations and reference items for each workflow step in the long methods text when they are available in the structured context.",
            "Avoid repeating the same workflow description when adjacent sections can be phrased concisely.",
            "Do not invent tools, organisms, references, parameters, or citations.",
            "Do not mention workflow steps that are absent from the structured context.",
            "Return JSON with keys: methods_long, methods_short, methods_references.",
            "",
            "Structured context:",
            yaml.safe_dump(context, sort_keys=False),
            "",
            "Deterministic long draft:",
            long_draft,
            "",
            "Deterministic short draft:",
            short_draft,
            "",
            "References:",
            references,
        ]
    )


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        return stripped[start : end + 1]
    return stripped


def call_openai_compatible_api(
    *,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
    prompt: str,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": "You write accurate publication methods from workflow provenance."},
            {"role": "user", "content": prompt},
        ],
    }
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    raw = json.loads(body)
    content = str(raw.get("choices", [{}])[0].get("message", {}).get("content") or "")
    try:
        parsed = json.loads(extract_json_object(content))
    except Exception:
        parsed = {"methods_long": content, "methods_short": "", "methods_references": ""}
    return {"raw": raw, "parsed": parsed}


def llm_config_default_path(project_dir: Path) -> Path:
    return project_dir / ".methods_llm.yaml"


def resolve_llm_settings(args: argparse.Namespace, project_dir: Path) -> dict[str, Any]:
    config_path = Path(args.llm_config).expanduser() if str(args.llm_config).strip() else None
    if config_path is None:
        env_path = os.environ.get("LINKAR_LLM_CONFIG", "").strip()
        if env_path:
            config_path = Path(env_path).expanduser()
    if config_path is None:
        default_path = llm_config_default_path(project_dir)
        if default_path.exists():
            config_path = default_path
    config: dict[str, Any] = {}
    if config_path is not None:
        if not config_path.is_absolute():
            config_path = (project_dir / config_path).resolve()
        if config_path.is_dir():
            directory_default = config_path / ".methods_llm.yaml"
            config_path = directory_default if directory_default.exists() else None
        if config_path is not None:
            config = load_mapping(config_path)

    api_key = os.environ.get("LINKAR_LLM_API_KEY", "").strip()
    api_key_source = "LINKAR_LLM_API_KEY" if api_key else ""
    api_key_env_name = str(config.get("api_key_env") or "").strip()
    if not api_key and api_key_env_name:
        api_key = os.environ.get(api_key_env_name, "").strip()
        api_key_source = api_key_env_name if api_key else ""
    if not api_key:
        api_key = str(config.get("api_key") or config.get("token") or "").strip()
        api_key_source = "llm_config" if api_key else ""

    base_url = (
        str(args.llm_base_url).strip()
        or os.environ.get("LINKAR_LLM_BASE_URL", "").strip()
        or str(config.get("base_url") or "").strip()
    )
    model = (
        str(args.llm_model).strip()
        or os.environ.get("LINKAR_LLM_MODEL", "").strip()
        or str(config.get("model") or "").strip()
    )
    temperature = args.llm_temperature
    if not str(args.llm_temperature).strip() and config.get("temperature") is not None:
        try:
            temperature = float(config.get("temperature"))
        except Exception:
            temperature = 0.2

    return {
        "config_path": str(config_path) if config_path is not None else "",
        "config": compact_mapping(config),
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
        "api_key_source": api_key_source,
    }


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    project_dir = Path(args.project_dir).expanduser()
    if not project_dir.is_absolute():
        project_dir = (Path.cwd() / project_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    project_file = project_dir / "project.yaml"
    if not project_file.exists():
        raise SystemExit(f"project.yaml not found: {project_file}")

    template_dir = Path(__file__).resolve().parent
    project_data = load_yaml(project_file)
    catalog = load_yaml(template_dir / "methods_catalog.yaml")
    runs, citation_ids = collect_run_context(project_dir, project_data, catalog)
    project_api = resolve_project_api_metadata(project_data, args.metadata_api_url)
    llm_settings = resolve_llm_settings(args, project_dir)
    context = {
        "project": {
            "id": project_data.get("id") or project_dir.name,
            "path": str(project_dir),
            "author": project_author_text(project_data),
        },
        "project_api": project_api,
        "style": args.style,
        "llm_settings": compact_mapping(
            {
                "config_path": llm_settings.get("config_path"),
                "base_url": llm_settings.get("base_url"),
                "model": llm_settings.get("model"),
                "temperature": llm_settings.get("temperature"),
                "api_key_source": llm_settings.get("api_key_source"),
            }
        ),
        "runs": runs,
        "citation_ids": citation_ids,
    }
    long_draft = deterministic_long_methods(context, catalog)
    short_draft = deterministic_short_methods(context)
    refs = references_markdown(citation_ids, catalog)
    prompt = build_prompt(context, long_draft, short_draft, refs, args.style)

    response_payload: dict[str, Any] = {
        "used_llm": False,
        "reason": "LLM polishing disabled.",
        "llm_settings": context["llm_settings"],
    }
    if parse_bool(args.use_llm):
        base_url = str(llm_settings.get("base_url") or "").strip()
        model = str(llm_settings.get("model") or "").strip()
        api_key = str(llm_settings.get("api_key") or "").strip()
        if base_url and model and api_key:
            try:
                response_payload = call_openai_compatible_api(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    temperature=float(llm_settings.get("temperature") or 0.2),
                    prompt=prompt,
                )
                response_payload["used_llm"] = True
                response_payload["llm_settings"] = context["llm_settings"]
                parsed = response_payload.get("parsed") if isinstance(response_payload.get("parsed"), dict) else {}
                long_draft = str(parsed.get("methods_long") or long_draft)
                short_draft = str(parsed.get("methods_short") or short_draft)
                refs = str(parsed.get("methods_references") or refs)
            except Exception as exc:
                response_payload = {
                    "used_llm": False,
                    "reason": f"LLM polishing failed: {exc}",
                    "llm_settings": context["llm_settings"],
                }
        else:
            response_payload = {
                "used_llm": False,
                "reason": "LLM polishing requested but API key, base URL, or model was missing.",
                "llm_settings": context["llm_settings"],
            }

    write_yaml(results_dir / "methods_context.yaml", context)
    (results_dir / "methods_long.md").write_text(long_draft, encoding="utf-8")
    (results_dir / "methods_short.md").write_text(short_draft, encoding="utf-8")
    (results_dir / "methods_references.md").write_text(refs, encoding="utf-8")
    (results_dir / "methods_prompt.md").write_text(prompt, encoding="utf-8")
    write_json(results_dir / "methods_response.json", response_payload)

    print(f"[info] wrote {results_dir / 'methods_context.yaml'}")
    print(f"[info] wrote {results_dir / 'methods_long.md'}")
    print(f"[info] wrote {results_dir / 'methods_short.md'}")
    print(f"[info] wrote {results_dir / 'methods_references.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
