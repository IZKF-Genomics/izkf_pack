#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shlex
from glob import glob
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
    parser.add_argument("--use-llm", default="true")
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
    return base_label


def infer_run_variant_name(entry: dict[str, Any], run_dir: Path | None) -> str:
    template_id = str(entry.get("id") or "").strip().lower()
    if run_dir is None:
        return ""

    candidate = run_dir.name.strip()
    if not candidate:
        return ""

    normalized = candidate.lower()
    prefixes = {
        template_id,
        "nfcore_3mrnaseq",
        "nfcore",
        "dgea",
        "ercc",
    }
    for prefix in prefixes:
        if prefix and normalized.startswith(prefix + "_"):
            candidate = candidate[len(prefix) + 1 :]
            break

    candidate = candidate.strip("_- ")
    if not candidate:
        return ""

    words = [part for part in re.split(r"[_\-\s]+", candidate) if part]
    return " ".join(word.capitalize() for word in words)


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


def project_assay_description(context: dict[str, Any]) -> str:
    meta = project_metadata(context)
    if not meta:
        return ""

    assay = format_publication_value("application", meta.get("application"))
    library_kit = normalize_id_value(meta.get("library_kit"))
    index_kit = normalize_id_value(meta.get("index_kit"))
    umi = normalize_id_value(meta.get("umi"))
    spike_in = normalize_id_value(meta.get("spike_in"))
    read_type = normalize_id_value(meta.get("read_type"))
    read1 = normalize_id_value(meta.get("cycles_read1"))
    read2 = normalize_id_value(meta.get("cycles_read2"))
    index1 = normalize_id_value(meta.get("cycles_index1"))
    index2 = normalize_id_value(meta.get("cycles_index2"))
    sequencer = normalize_id_value(meta.get("sequencer"))
    instrument = normalize_id_value(meta.get("instrument"))
    sequencing_kit = normalize_id_value(meta.get("sequencing_kit"))
    phix = normalize_id_value(meta.get("phix_percentage"))

    prep_bits = [item for item in [library_kit, index_kit, umi] if item]
    if not prep_bits and not any([assay, sequencer, sequencing_kit]):
        return ""

    assay_prefix = f"{assay} libraries" if assay else "Libraries"
    sentence = f"{assay_prefix} were prepared"
    if prep_bits:
        if len(prep_bits) == 1:
            sentence += f" using {prep_bits[0]}"
        elif len(prep_bits) == 2:
            sentence += f" using {prep_bits[0]} and {prep_bits[1]}"
        else:
            sentence += f" using {', '.join(prep_bits[:-1])}, and {prep_bits[-1]}"
    if spike_in:
        sentence += f"; {spike_in} was included as spike-in control"
    sentence += "."

    sequencing_sentence = ""
    if read_type == "single-end" and read1:
        sequencing_sentence = f"Single-end sequencing ({read1} cycles)"
    elif read_type == "paired-end" and read1 and read2:
        sequencing_sentence = f"Paired-end sequencing ({read1} + {read2} cycles)"
    elif read_type:
        sequencing_sentence = f"{read_type.capitalize()} sequencing"

    if sequencing_sentence:
        platform = " / ".join(item for item in [sequencer, instrument] if item)
        sequencing_sentence += " was performed"
        if platform:
            sequencing_sentence += f" on {platform}"
        if sequencing_kit:
            sequencing_sentence += f" using the {sequencing_kit}"
        if index1 and index2:
            if index1 == index2:
                sequencing_sentence += f" with dual {index1}-cycle indices"
            else:
                sequencing_sentence += f" with index reads of {index1} and {index2} cycles"
        elif index1 or index2:
            sequencing_sentence += f" with index reads of {index1 or index2} cycles"
        if phix:
            phix_text = phix.removesuffix(".0") if phix.endswith(".0") else phix
            sequencing_sentence += f" and {phix_text}% PhiX"
        sequencing_sentence += "."

    return " ".join(part for part in [sentence, sequencing_sentence] if part).strip()


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
    if run_dir is not None:
        versions.extend(infer_additional_versions(run_dir))
    return versions


def infer_additional_versions(run_dir: Path) -> list[dict[str, Any]]:
    inferred: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, version: str, source: str, path: Path) -> None:
        normalized_name = normalize_id_value(name)
        normalized_version = normalize_id_value(version)
        if not normalized_name or not normalized_version:
            return
        key = (normalized_name.lower(), normalized_version)
        if key in seen:
            return
        seen.add(key)
        inferred.append(
            {
                "name": normalized_name,
                "version": normalized_version,
                "source": source,
                "path": str(path),
            }
        )

    for tool_name in ("star", "salmon"):
        for raw_path in glob(str(run_dir / "work" / "**" / "versions.yml"), recursive=True):
            path = Path(raw_path)
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            match = re.search(rf"^\s*{re.escape(tool_name)}:\s*([^\s]+)", text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                add(tool_name, match.group(1), "inferred_from_versions_yml", path)
                break

    pixi_lock = run_dir / "pixi.lock"
    if pixi_lock.exists():
        text = pixi_lock.read_text(encoding="utf-8", errors="replace")
        for package_name, tool_name in [
            ("bioconductor-deseq2", "DESeq2"),
            ("bioconductor-clusterprofiler", "clusterProfiler"),
        ]:
            match = re.search(rf"{re.escape(package_name)}-([0-9]+(?:\.[0-9]+)+)-", text, flags=re.IGNORECASE)
            if match:
                add(tool_name, match.group(1), "inferred_from_pixi_lock", pixi_lock)

    return inferred


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


def resolve_catalog_citations(template_id: str, catalog_entry: dict[str, Any], params: dict[str, Any]) -> list[str]:
    citations = [str(item).strip() for item in (catalog_entry.get("citations") or []) if str(item).strip()]
    if template_id == "scverse_scrna_prep":
        doublet_method = normalize_id_value(params.get("doublet_method"))
        if doublet_method == "scrublet":
            citations.append("scrublet")
    if template_id == "scverse_scrna_integrate":
        method = normalize_id_value(params.get("integration_method"))
        if method == "scvi":
            citations.append("scvi")
        elif method == "scanvi":
            citations.extend(["scvi", "scanvi"])
        elif method in {"harmony", "bbknn", "scanorama"}:
            citations.append(method)
        if parse_bool(params.get("run_scib_metrics"), default=False):
            citations.append("scib")
    if template_id == "scverse_scrna_annotate":
        method = normalize_id_value(params.get("annotation_method"))
        if method == "celltypist":
            citations.append("celltypist")
    return unique_ordered(citations)


def collect_run_context(
    project_dir: Path,
    project_data: dict[str, Any],
    catalog: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    runs: list[dict[str, Any]] = []
    citation_ids: list[str] = []
    template_counts: dict[str, int] = {}
    templates = project_data.get("templates") or []
    if isinstance(templates, list):
        for entry in templates:
            if not isinstance(entry, dict):
                continue
            template_id = str(entry.get("id") or "").strip()
            if not template_id or template_id in {"export", "methods"}:
                continue
            template_counts[template_id] = template_counts.get(template_id, 0) + 1
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
        citations = resolve_catalog_citations(template_id, catalog_entry, params)
        citation_ids.extend(str(item) for item in citations if str(item).strip())
        runtime_command = load_runtime_command(project_dir, run_dir, outputs)
        label = run_display_label(entry, catalog_entry, run_dir)
        params_name = str(params.get("name") or "").strip()
        if template_counts.get(template_id, 0) > 1 and not params_name:
            variant = infer_run_variant_name(entry, run_dir)
            if variant and label == str(catalog_entry.get("label") or template_id).strip():
                label = f"{label}: {variant}"
        runs.append(
            {
                "order": index,
                "template": template_id,
                "version": entry.get("template_version"),
                "instance_id": entry.get("instance_id"),
                "label": label,
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
    return runs, unique_ordered(citation_ids)


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
        "deseq2": "DESeq2",
        "clusterprofiler": "clusterProfiler",
        "salmon": "Salmon",
        "star": "STAR",
        "nextflow": "Nextflow",
        "quarto": "Quarto",
        "pixi": "pixi",
    }
    return mapping.get(name.lower(), name)


def version_map_for_run(run: dict[str, Any]) -> dict[str, str]:
    version_map: dict[str, str] = {}
    for item in run.get("software_versions") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if not name:
            continue
        cleaned = clean_runtime_version(
            str(item.get("name") or ""),
            normalize_id_value(item.get("version")),
            normalize_id_value(item.get("raw")),
        )
        if cleaned and name not in version_map:
            version_map[name] = cleaned
    return version_map


def humanize_base_genome_identifier(text: str) -> str:
    value = normalize_id_value(text)
    if not value:
        return ""

    known = {
        "GRCh38": "Human genome (GRCh38)",
        "hg38": "Human genome (hg38)",
        "hg19": "Human genome (hg19)",
        "GRCm39": "Mouse genome (GRCm39)",
        "mm10": "Mouse genome (mm10)",
        "mm39": "Mouse genome (mm39)",
    }
    if value in known:
        return known[value]

    species_matches = [
        (r"^Sscrofa(.+)$", "Sus scrofa genome"),
        (r"^Mmulatta(.+)$", "Macaca mulatta genome"),
        (r"^Rnorvegicus(.+)$", "Rattus norvegicus genome"),
        (r"^Btaurus(.+)$", "Bos taurus genome"),
        (r"^Ggallus(.+)$", "Gallus gallus genome"),
        (r"^Drerio(.+)$", "Danio rerio genome"),
    ]
    for pattern, species_label in species_matches:
        match = re.match(pattern, value)
        if match:
            build = match.group(1).strip("._- ")
            if build:
                return f"{species_label} (build {build})"
            return species_label

    return value


def humanize_genome_identifier(text: str) -> str:
    value = normalize_id_value(text)
    if not value:
        return ""
    if value.endswith("_with_ERCC"):
        base = humanize_base_genome_identifier(value.removesuffix("_with_ERCC"))
        return f"{base} augmented with ERCC spike-in sequences"
    return humanize_base_genome_identifier(value)


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
    if key == "genome":
        return humanize_genome_identifier(text)
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

    requested_genome_raw = normalize_id_value(params.get("genome") or "")
    effective_genome_raw = normalize_id_value(params.get("effective_genome") or params.get("genome") or "")
    requested_genome = format_publication_value("genome", requested_genome_raw)
    effective_genome = format_publication_value("genome", effective_genome_raw)
    block = genome_blocks.get(effective_genome_raw) or {}
    fasta_path = normalize_id_value(block.get("fasta"))
    gtf_path = normalize_id_value(block.get("gtf"))
    annotation_version = derive_annotation_version(gtf_path)

    if not annotation_version and effective_genome_raw.endswith("_with_ERCC"):
        base_block = genome_blocks.get(effective_genome_raw.removesuffix("_with_ERCC")) or {}
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
        genome = format_publication_value(
            "genome",
            runtime_command_value_after_flag(run, "--genome") or params.get("effective_genome") or params.get("genome") or "",
        ) or format_publication_value("genome", params.get("effective_genome") or params.get("genome") or "")
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
        umi_runtime_value = format_publication_value("umi", params.get("umi") or "")
        if runtime_command_has_flag(run, "--with_umi"):
            items.append(("UMI handling", umi_runtime_value or "enabled"))
            extract_method = runtime_command_value_after_flag(run, "--umitools_extract_method")
            if extract_method:
                items.append(("UMI extract method", extract_method))
            bc_pattern = runtime_command_value_after_flag(run, "--umitools_bc_pattern")
            if bc_pattern:
                items.append(("UMI barcode pattern", bc_pattern))

    if template == "nfcore_methylseq":
        genome = format_publication_value(
            "genome",
            runtime_command_value_after_flag(run, "--genome") or params.get("genome") or "",
        ) or format_publication_value("genome", params.get("genome") or "")
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
    command = runtime_command.get("command")
    command_parts: list[str] = []
    if isinstance(command, list):
        command_parts = [str(part) for part in command if str(part).strip()]
    if not command_parts:
        command_pretty = normalize_id_value(runtime_command.get("command_pretty"))
        if command_pretty:
            try:
                command_parts = shlex.split(command_pretty)
            except ValueError:
                command_parts = [command_pretty]
    if not command_parts:
        return ""
    return "```bash\n" + format_multiline_shell_command(command_parts) + "\n```"


def format_multiline_shell_command(command_parts: list[str]) -> str:
    if not command_parts:
        return ""

    def render_part(part: str) -> str:
        if part.startswith("-") and "=" in part:
            flag, value = part.split("=", 1)
            return f"{flag}={shlex.quote(value)}"
        return shlex.quote(part)

    leading: list[str] = []
    remainder_start = 0
    for index, part in enumerate(command_parts):
        if part.startswith("-"):
            remainder_start = index
            break
        leading.append(shlex.quote(part))
    else:
        return " ".join(leading)

    lines = [" ".join(leading)] if leading else []
    index = remainder_start
    while index < len(command_parts):
        part = command_parts[index]
        rendered = render_part(part)
        if "=" in part or not part.startswith("-"):
            lines.append(rendered)
            index += 1
            continue
        if index + 1 < len(command_parts) and not command_parts[index + 1].startswith("-"):
            next_part = shlex.quote(command_parts[index + 1])
            lines.append(f"{rendered} {next_part}")
            index += 2
            continue
        lines.append(rendered)
        index += 1

    if len(lines) == 1:
        return lines[0]
    return " \\\n".join(lines)


def collect_setting_bullets(run: dict[str, Any], context: dict[str, Any]) -> list[str]:
    template = str(run.get("template") or "").strip()
    params = merged_run_params(run)
    items: list[tuple[str, str]] = []

    if template == "nfcore_3mrnaseq":
        reference = format_publication_value(
            "genome",
            runtime_command_value_after_flag(run, "--genome") or params.get("effective_genome") or params.get("genome") or "",
        ) or format_publication_value("genome", params.get("effective_genome") or params.get("genome") or "")
        spikein = format_publication_value("spikein", params.get("spikein") or "")
        umi_value = format_publication_value("umi", params.get("umi") or "")
        if reference:
            items.append(("Reference genome", reference))
        if spikein:
            items.append(("Spike-in control", spikein))
        if runtime_command_has_flag(run, "--with_umi"):
            items.append(("UMI handling", umi_value or "enabled"))
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
        assay_description = project_assay_description(context)
        if assay_description:
            lines.append("")
            lines.append(assay_description)
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


def clean_kit_name(text: str) -> str:
    value = normalize_id_value(text)
    if not value:
        return ""
    value = re.sub(r"\s+for Illumina$", "", value, flags=re.IGNORECASE).strip()
    return value


def short_r_version(text: str) -> str:
    value = normalize_id_value(text)
    match = re.search(r"\bversion\s+([0-9]+(?:\.[0-9]+)+)", value, flags=re.IGNORECASE)
    if match:
        return f"R {match.group(1)}"
    return value


def unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        ordered.append(item)
        seen.add(item)
    return ordered


def numbered_references_markdown(citation_ids: list[str], catalog: dict[str, Any]) -> str:
    refs = catalog.get("references") if isinstance(catalog.get("references"), dict) else {}
    lines = ["References"]
    if not citation_ids:
        lines.append("1. No template-level references were selected.")
        return "\n".join(lines) + "\n"
    for index, citation_id in enumerate(citation_ids, start=1):
        entry = refs.get(citation_id) if isinstance(refs, dict) else None
        if isinstance(entry, dict):
            text = str(entry.get("text") or citation_id).strip()
            url = str(entry.get("url") or "").strip()
            lines.append(f"{index}. {text}" + (f" {url}" if url else ""))
        else:
            lines.append(f"{index}. {citation_id}")
    return "\n".join(lines) + "\n"


def citation_number_map(citation_ids: list[str]) -> dict[str, int]:
    return {citation_id: index for index, citation_id in enumerate(unique_ordered(citation_ids), start=1)}


def inline_citations(citation_ids: list[str], number_map: dict[str, int]) -> str:
    numbers = [number_map[citation_id] for citation_id in citation_ids if citation_id in number_map]
    numbers = list(dict.fromkeys(numbers))
    if not numbers:
        return ""
    rendered = ", ".join(str(number) for number in numbers)
    return f" [{rendered}]"


def short_assay_sentence(context: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    meta = project_metadata(context)
    assay = format_publication_value("application", meta.get("application"))
    library_kit = normalize_id_value(meta.get("library_kit"))
    index_kit = normalize_id_value(meta.get("index_kit"))
    sequencer = normalize_id_value(meta.get("sequencer"))
    instrument = normalize_id_value(meta.get("instrument"))
    sequencing_kit = normalize_id_value(meta.get("sequencing_kit"))
    phix = normalize_id_value(meta.get("phix_percentage"))
    cycles_read1 = normalize_id_value(meta.get("cycles_read1"))
    cycles_index1 = normalize_id_value(meta.get("cycles_index1"))
    cycles_index2 = normalize_id_value(meta.get("cycles_index2"))
    cycles_read2 = normalize_id_value(meta.get("cycles_read2"))
    read_type = normalize_id_value(meta.get("read_type"))
    any_umi = any(runtime_command_has_flag(run, "--with_umi") for run in runs)
    umi_label = normalize_id_value(meta.get("umi")) if any_umi else ""
    spike_in = normalize_id_value(meta.get("spike_in"))

    if not any([assay, library_kit, index_kit, sequencer, sequencing_kit]):
        return ""

    assay_prefix = f"{assay} libraries" if assay else "Sequencing libraries"
    sentence = f"{assay_prefix} were prepared"
    if library_kit:
        sentence += f" using the {library_kit}"
    if index_kit:
        sentence += f" with {index_kit}"
    if umi_label:
        connector = " and the " if library_kit or index_kit else " using the "
        sentence += f"{connector}{umi_label}"
    if spike_in:
        sentence += f"; {spike_in} was used as spike-in control"
    sentence += "."

    sequencing_bits: list[str] = []
    if read_type == "single-end" and cycles_read1:
        sequencing_bits.append(f"Single-end sequencing ({cycles_read1} cycles)")
    elif read_type == "paired-end" and cycles_read1 and cycles_read2:
        sequencing_bits.append(f"Paired-end sequencing ({cycles_read1} + {cycles_read2} cycles)")
    elif read_type:
        sequencing_bits.append(f"{read_type.capitalize()} sequencing")
    else:
        sequencing_bits.append("Sequencing")

    if sequencer and instrument:
        sequencing_bits.append(f"was performed on a {sequencer} instrument ({instrument})")
    elif sequencer:
        sequencing_bits.append(f"was performed on {sequencer}")
    elif instrument:
        sequencing_bits.append(f"was performed on instrument {instrument}")
    if sequencing_kit:
        sequencing_bits.append(f"using the {sequencing_kit}")
    if cycles_index1 and cycles_index2 and cycles_index1 == cycles_index2:
        sequencing_bits.append(f"with dual {cycles_index1}-cycle indices")
    elif cycles_index1 or cycles_index2:
        index_bits = "/".join(part for part in [cycles_index1, cycles_index2] if part)
        sequencing_bits.append(f"with index reads of {index_bits} cycles")
    if phix:
        phix_text = phix.removesuffix(".0") if phix.endswith(".0") else phix
        sequencing_bits.append(f"and {phix_text}% PhiX")

    return sentence + " " + " ".join(sequencing_bits).strip() + "."


def short_demultiplex_sentence(runs: list[dict[str, Any]], citation_map: dict[str, int]) -> str:
    run = next((run for run in runs if str(run.get("template") or "").strip() == "demultiplex"), None)
    if not isinstance(run, dict):
        return ""
    version_map = {
        str(item.get("name") or "").lower(): clean_runtime_version(
            str(item.get("name") or ""),
            normalize_id_value(item.get("version")),
            normalize_id_value(item.get("raw")),
        )
        for item in (run.get("software_versions") or [])
        if isinstance(item, dict)
    }
    bcl_version = version_map.get("bcl-convert", "")
    bcl_phrase = "BCL Convert"
    if bcl_version:
        match = re.search(r"Version\s+([0-9][^\s]*)", bcl_version)
        if match:
            bcl_phrase += f" v{match.group(1)}"
    qc_tool = format_publication_value("qc_tool", merged_run_params(run).get("qc_tool") or "")
    qc_bits = []
    if qc_tool:
        qc_bits.append(qc_tool)
    if (run.get("outputs") if isinstance(run.get("outputs"), dict) else {}).get("multiqc_report"):
        qc_bits.append("MultiQC")
    citations = ["bcl_convert"]
    if qc_tool.lower() == "falco":
        citations.append("falco")
    if "MultiQC" in qc_bits:
        citations.append("multiqc")
    sentence = f"Sequencing reads were demultiplexed into FASTQ files with {bcl_phrase}."
    if qc_bits:
        if len(qc_bits) == 1:
            sentence += f" Read quality was assessed with {qc_bits[0]}."
        else:
            sentence += f" Read quality was assessed with {qc_bits[0]} and summarized with {qc_bits[1]}."
    return sentence.rstrip(".") + inline_citations(citations, citation_map) + "."


def short_nfcore_sentence(runs: list[dict[str, Any]], citation_map: dict[str, int]) -> str:
    nfcore_runs = [run for run in runs if str(run.get("template") or "").strip() == "nfcore_3mrnaseq"]
    if not nfcore_runs:
        return ""
    runtime_command = nfcore_runs[0].get("runtime_command") if isinstance(nfcore_runs[0].get("runtime_command"), dict) else {}
    pipeline_version = normalize_id_value(runtime_command.get("pipeline_version"))
    nextflow_version = ""
    star_version = ""
    salmon_version = ""
    for run in nfcore_runs:
        version_map = version_map_for_run(run)
        star_version = star_version or version_map.get("star", "")
        salmon_version = salmon_version or version_map.get("salmon", "")
        for item in run.get("software_versions") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "").lower() == "nextflow":
                nextflow_version = clean_runtime_version(
                    "nextflow",
                    normalize_id_value(item.get("version")),
                    normalize_id_value(item.get("raw")),
                )
                break
        if nextflow_version:
            break

    base = "RNA-seq data were processed with nf-core/rnaseq"
    if pipeline_version:
        base += f" v{pipeline_version}"
    if nextflow_version:
        base += f" via Nextflow {nextflow_version}"
    base += ", using STAR"
    if star_version:
        base += f" {star_version}"
    base += " for alignment and Salmon"
    if salmon_version:
        base += f" {salmon_version}"
    base += " for quantification"

    run_specific_bits: list[str] = []
    for run in nfcore_runs:
        label = str(run.get("label") or "").lower()
        cohort = ""
        if "liver" in label:
            cohort = "liver"
        elif "bile" in label:
            cohort = "bile duct"
        genome = format_publication_value("genome", runtime_command_value_after_flag(run, "--genome") or "")
        bits: list[str] = []
        if genome:
            bits.append(f"against {genome}")
        if runtime_command_has_flag(run, "--with_umi"):
            bits.append("with UMI-aware extraction enabled")
        featurecounts_group = runtime_command_value_after_flag(run, "--featurecounts_group_type")
        if featurecounts_group:
            bits.append(f"using featureCounts grouping by {featurecounts_group}")
        if bits:
            if cohort:
                run_specific_bits.append(f"{cohort} libraries were processed " + ", ".join(bits))
            else:
                run_specific_bits.append("libraries were processed " + ", ".join(bits))

    sentence = base + inline_citations(
        ["nextflow", "nfcore_framework", "nfcore_rnaseq", "star", "salmon"],
        citation_map,
    ) + "."
    if run_specific_bits:
        sentence += " " + " ".join(
            piece[0].upper() + piece[1:] + "." if piece and piece[-1] != "." else piece for piece in run_specific_bits
        )
    return sentence


def short_downstream_sentence(runs: list[dict[str, Any]], citation_map: dict[str, int]) -> str:
    dgea_runs = [run for run in runs if str(run.get("template") or "").strip() == "dgea"]
    ercc_runs = [run for run in runs if str(run.get("template") or "").strip() == "ercc"]
    scrna_runs = [run for run in runs if str(run.get("template") or "").strip() == "scverse_scrna_prep"]
    integrate_runs = [run for run in runs if str(run.get("template") or "").strip() == "scverse_scrna_integrate"]
    annotate_runs = [run for run in runs if str(run.get("template") or "").strip() == "scverse_scrna_annotate"]
    parts: list[str] = []
    if dgea_runs:
        cohort_names = unique_ordered(
            [
                normalize_id_value((run.get("params") if isinstance(run.get("params"), dict) else {}).get("name"))
                for run in dgea_runs
            ]
        )
        cohort_text = ""
        if cohort_names:
            if len(cohort_names) == 1:
                cohort_text = f" for the {cohort_names[0]} cohort"
            else:
                cohort_text = " for the " + " and ".join(cohort_names) + " cohorts"
        r_version = ""
        deseq2_version = ""
        clusterprofiler_version = ""
        for run in dgea_runs:
            version_map = version_map_for_run(run)
            deseq2_version = deseq2_version or version_map.get("deseq2", "")
            clusterprofiler_version = clusterprofiler_version or version_map.get("clusterprofiler", "")
            for item in run.get("software_versions") or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("name") or "").lower() == "r":
                    r_version = clean_runtime_version(
                        "R",
                        normalize_id_value(item.get("version")),
                        normalize_id_value(item.get("raw")),
                    )
                    break
            if r_version:
                break
        sentence = f"Differential expression analyses{cohort_text} were prepared in R/Quarto workspaces configured for DESeq2"
        if deseq2_version:
            sentence += f" {deseq2_version}"
        sentence += "-based reporting from quantification outputs and sample metadata"
        if r_version:
            sentence += f", using {short_r_version(r_version)}"
        if clusterprofiler_version:
            sentence += f", with optional clusterProfiler {clusterprofiler_version} enrichment workflows"
        parts.append(
            sentence
            + inline_citations(["deseq2", "clusterprofiler", "quarto"], citation_map)
            + "."
        )
    if ercc_runs:
        parts.append(
            "ERCC spike-in performance was additionally assessed from Salmon quantification outputs in a Quarto-rendered quality-control report"
            + inline_citations(["ercc_spikein", "salmon", "quarto"], citation_map)
            + "."
        )
    if scrna_runs:
        params = merged_run_params(scrna_runs[0])
        sentence = (
            "Single-cell RNA-seq preprocessing and quality control were carried out in a Scanpy/scverse workspace "
            "with cell-level QC, highly variable gene selection, principal component analysis, UMAP embedding, and Leiden clustering"
        )
        doublet_method = normalize_id_value(params.get("doublet_method"))
        citation_ids = ["scanpy", "umap", "leiden", "quarto"]
        if doublet_method == "scrublet":
            sentence += ", with Scrublet-based doublet scoring"
            citation_ids.append("scrublet")
        sentence += ", and reported in a Quarto QC notebook"
        parts.append(sentence + inline_citations(citation_ids, citation_map) + ".")
    if integrate_runs:
        params = merged_run_params(integrate_runs[0])
        method = normalize_id_value(params.get("integration_method"))
        method_label_map = {
            "scvi": "scVI latent modeling",
            "scanvi": "semi-supervised scANVI latent modeling",
            "harmony": "Harmony batch correction",
            "bbknn": "BBKNN graph correction",
            "scanorama": "Scanorama integration",
        }
        sentence = (
            "Prepared single-cell datasets were additionally integrated in a Scanpy/scverse workspace "
            f"using {method_label_map.get(method, 'a configured integration backend')}, followed by neighbor-graph reconstruction, UMAP embedding, Leiden clustering, and quantitative integration diagnostics"
        )
        citation_ids = ["scanpy", "umap", "leiden", "quarto"]
        if method == "scvi":
            citation_ids.append("scvi")
        elif method == "scanvi":
            citation_ids.extend(["scvi", "scanvi"])
        elif method in {"harmony", "bbknn", "scanorama"}:
            citation_ids.append(method)
        if parse_bool(params.get("run_scib_metrics"), default=False):
            sentence += ", including optional scIB benchmarking"
            citation_ids.append("scib")
        sentence += ", and reported in a Quarto QC notebook"
        parts.append(sentence + inline_citations(citation_ids, citation_map) + ".")
    if annotate_runs:
        params = merged_run_params(annotate_runs[0])
        method = normalize_id_value(params.get("annotation_method"))
        cluster_key = normalize_id_value(params.get("cluster_key")) or "leiden"
        sentence = (
            "Cell identities were then reviewed in a Scanpy/scverse annotation workspace "
            f"using cluster-level summaries keyed on {cluster_key}"
        )
        citation_ids = ["scanpy", "quarto"]
        if method == "celltypist":
            sentence += ", CellTypist label transfer, classifier confidence summaries, and optional marker-based validation"
            citation_ids.append("celltypist")
        else:
            sentence += ", automated label transfer, classifier confidence summaries, and optional marker-based validation"
        sentence += ", while unresolved clusters were retained as unknown pending manual review"
        parts.append(sentence + inline_citations(citation_ids, citation_map) + ".")
    return " ".join(parts)


def deterministic_short_methods(context: dict[str, Any], catalog: dict[str, Any]) -> str:
    runs = [
        run
        for run in context.get("runs") or []
        if isinstance(run, dict) and parse_bool(run.get("publication_relevance"), default=True)
    ]
    if not runs:
        return "No publication-relevant workflow steps were identified in the recorded project history.\n"

    ordered_citation_ids = [str(item) for item in context.get("citation_ids") or [] if str(item).strip()]
    citation_map = citation_number_map(ordered_citation_ids)
    sentences = [
        short_assay_sentence(context, runs),
        short_demultiplex_sentence(runs, citation_map),
        short_nfcore_sentence(runs, citation_map),
        short_downstream_sentence(runs, citation_map),
    ]
    fallback_sentences = [build_publication_summary(run) for run in runs if build_publication_summary(run)]
    lead_paragraph = " ".join(sentence for sentence in sentences[:3] if sentence).strip()
    downstream_paragraph = " ".join(sentence for sentence in sentences[3:] if sentence).strip()
    text = "\n\n".join(paragraph for paragraph in [lead_paragraph, downstream_paragraph] if paragraph).strip()
    if not text:
        text = " ".join(fallback_sentences).strip()

    references = numbered_references_markdown(
        ordered_citation_ids,
        catalog,
    )
    return text.rstrip() + "\n\n" + references


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


def replace_references_section(text: str, references_block: str) -> str:
    body = text.rstrip()
    marker = re.search(r"(?im)^##\s+References\s*$|^References\s*$", body)
    if marker:
        body = body[: marker.start()].rstrip()
    return body + "\n\n" + references_block.strip() + "\n"


def render_inline_html(text: str) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    rendered: list[str] = []
    url_pattern = re.compile(r"(https?://[^\s<]+)")
    citation_pattern = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) >= 2:
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue
        escaped = html.escape(part)
        escaped = url_pattern.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', escaped)
        escaped = citation_pattern.sub(
            lambda m: "".join(
                f'<sup class="citation-ref" aria-label="Reference {html.escape(number.strip())}">{html.escape(number.strip())}</sup>'
                for number in m.group(1).split(",")
            ),
            escaped,
        )
        rendered.append(escaped)
    return "".join(rendered)


def slugify_heading(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "section"


def markdown_fragment_to_html(markdown_text: str) -> tuple[str, list[dict[str, str]]]:
    lines = markdown_text.splitlines()
    html_lines: list[str] = []
    sections: list[dict[str, str]] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_kind = ""
    in_code_block = False
    code_lines: list[str] = []
    heading_ids: dict[str, int] = {}

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(line.strip() for line in paragraph if line.strip())
            html_lines.append(f"<p>{render_inline_html(text)}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items, list_kind
        if list_items and list_kind:
            html_lines.append(f"<{list_kind}>")
            html_lines.extend(list_items)
            html_lines.append(f"</{list_kind}>")
        list_items = []
        list_kind = ""

    def flush_code_block() -> None:
        nonlocal code_lines
        html_lines.append("<pre><code>")
        html_lines.append(html.escape("\n".join(code_lines)))
        html_lines.append("</code></pre>")
        code_lines = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code_block:
                flush_code_block()
                in_code_block = False
            else:
                in_code_block = True
                code_lines = []
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            attrs = ""
            if level == 2:
                base_id = slugify_heading(title)
                count = heading_ids.get(base_id, 0) + 1
                heading_ids[base_id] = count
                heading_id = base_id if count == 1 else f"{base_id}-{count}"
                sections.append({"id": heading_id, "title": title})
                attrs = f' id="{heading_id}"'
            html_lines.append(f"<h{level}{attrs}>{render_inline_html(title)}</h{level}>")
            continue

        bullet = re.match(r"^- (.*)$", stripped)
        if bullet:
            flush_paragraph()
            if list_kind not in {"", "ul"}:
                flush_list()
            list_kind = "ul"
            list_items.append(f"<li>{render_inline_html(bullet.group(1).strip())}</li>")
            continue

        numbered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if numbered:
            flush_paragraph()
            if list_kind not in {"", "ol"}:
                flush_list()
            list_kind = "ol"
            list_items.append(f"<li>{render_inline_html(numbered.group(1).strip())}</li>")
            continue

        if list_kind:
            flush_list()
        paragraph.append(stripped)

    if in_code_block:
        flush_code_block()
    flush_paragraph()
    flush_list()
    return "\n".join(html_lines), sections


def render_methods_html(markdown_text: str, title: str) -> str:
    body, sections = markdown_fragment_to_html(markdown_text)
    escaped_title = html.escape(title)
    sidebar_links = "\n".join(
        f'          <li><a href="#{html.escape(section["id"])}">{html.escape(section["title"])}</a></li>'
        for section in sections
    )
    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>{escaped_title}</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f4f2ee; --paper: #ffffff; --ink: #20252a; --muted: #65707c; --line: #d7dde5; --accent: #1f4e79; --accent-soft: #e8f1fb; --code: #f4f6f8; --citation-bg: #fff2bf; --citation-ink: #7a5200; }",
            "    * { box-sizing: border-box; }",
            "    html { scroll-behavior: smooth; }",
            "    body { margin: 0; background: var(--bg); color: var(--ink); font-family: 'Iowan Old Style', 'Palatino Linotype', 'Book Antiqua', Georgia, serif; line-height: 1.72; }",
            "    .page { max-width: 1380px; margin: 0 auto; padding: 32px 24px 56px; display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 28px; align-items: start; }",
            "    .sidebar { position: sticky; top: 24px; align-self: start; background: rgba(255, 255, 255, 0.78); border: 1px solid var(--line); border-radius: 20px; padding: 24px 22px; backdrop-filter: blur(6px); }",
            "    .sidebar .eyebrow { margin: 0 0 0.45rem; font-family: Arial, Helvetica, sans-serif; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; color: var(--muted); }",
            "    .sidebar h1 { margin: 0 0 0.8rem; font-size: 1.5rem; line-height: 1.2; letter-spacing: -0.02em; }",
            "    .sidebar p { margin: 0 0 1.2rem; color: var(--muted); font-size: 0.96rem; }",
            "    .sidebar nav ul { list-style: none; margin: 0; padding: 0; }",
            "    .sidebar nav li + li { margin-top: 0.55rem; }",
            "    .sidebar nav a { color: var(--ink); text-decoration: none; display: block; padding: 0.45rem 0.6rem; border-radius: 10px; border: 1px solid transparent; }",
            "    .sidebar nav a:hover { background: var(--accent-soft); border-color: rgba(31, 78, 121, 0.16); }",
            "    article { background: var(--paper); border: 1px solid var(--line); border-radius: 24px; padding: 52px 64px; box-shadow: 0 22px 50px rgba(38, 48, 60, 0.08); }",
            "    article > h1:first-child { margin-top: 0; }",
            "    h1, h2, h3 { line-height: 1.25; color: #17212b; }",
            "    h1 { font-size: 2.35rem; margin: 0 0 1.5rem; letter-spacing: -0.03em; }",
            "    h2 { font-size: 1.38rem; margin: 2.4rem 0 0.95rem; padding-top: 1rem; border-top: 1px solid var(--line); scroll-margin-top: 24px; }",
            "    h3 { font-family: Arial, Helvetica, sans-serif; font-size: 0.83rem; margin: 1.55rem 0 0.6rem; color: var(--accent); text-transform: uppercase; letter-spacing: 0.16em; }",
            "    p, ul, ol, pre { margin: 0.92rem 0; }",
            "    p { font-size: 1.02rem; }",
            "    ul, ol { padding-left: 1.35rem; }",
            "    li + li { margin-top: 0.38rem; }",
            "    code { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace; background: var(--code); border: 1px solid #e0e5ea; border-radius: 4px; padding: 0.08rem 0.3rem; font-size: 0.9em; }",
            "    pre { background: #18212b; color: #f5f7fa; padding: 18px 20px; border-radius: 14px; overflow-x: auto; border: 1px solid rgba(255, 255, 255, 0.06); }",
            "    pre code { background: transparent; border: 0; color: inherit; padding: 0; }",
            "    a { color: var(--accent); text-decoration: none; border-bottom: 1px solid rgba(31, 78, 121, 0.24); }",
            "    a:hover { border-bottom-color: rgba(31, 78, 121, 0.68); }",
            "    .citation-ref { display: inline-flex; align-items: center; justify-content: center; min-width: 1.2rem; height: 1.2rem; margin-left: 0.12rem; padding: 0 0.24rem; border-radius: 999px; background: var(--citation-bg); color: var(--citation-ink); font-family: Arial, Helvetica, sans-serif; font-size: 0.64rem; font-weight: 700; line-height: 1; vertical-align: super; box-shadow: inset 0 0 0 1px rgba(122, 82, 0, 0.12); }",
            "    .citation-ref + .citation-ref { margin-left: 0.16rem; }",
            "    @media (max-width: 1080px) { .page { grid-template-columns: 1fr; } .sidebar { position: static; } article { padding: 38px 28px; } }",
            "    @media (max-width: 720px) { .page { padding: 16px 12px 28px; gap: 16px; } .sidebar { padding: 18px 16px; border-radius: 14px; } article { padding: 24px 18px; border-radius: 16px; } h1 { font-size: 1.85rem; } }",
            "  </style>",
            "</head>",
            "<body>",
            '  <main class="page">',
            '    <aside class="sidebar">',
            '      <p class="eyebrow">Methods Draft</p>',
            f"      <h1>{escaped_title}</h1>",
            "      <p>Clean publication-style rendering with section navigation and readable citations.</p>",
            "      <nav aria-label=\"Methods sections\">",
            "        <ul>",
            sidebar_links,
            "        </ul>",
            "      </nav>",
            "    </aside>",
            "    <article>",
            body,
            "    </article>",
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def important_short_version_phrases(context: dict[str, Any]) -> list[str]:
    phrases: list[str] = []
    for run in context.get("runs") or []:
        if not isinstance(run, dict):
            continue
        template = str(run.get("template") or "").strip()
        version_map = version_map_for_run(run)
        if template == "nfcore_3mrnaseq":
            if version_map.get("star"):
                phrases.append(f"STAR {version_map['star']}")
            if version_map.get("salmon"):
                phrases.append(f"Salmon {version_map['salmon']}")
        elif template == "dgea":
            if version_map.get("deseq2"):
                phrases.append(f"DESeq2 {version_map['deseq2']}")
            if version_map.get("clusterprofiler"):
                phrases.append(f"clusterProfiler {version_map['clusterprofiler']}")
            r_version = version_map.get("r")
            if r_version:
                phrases.append(short_r_version(r_version))
    return unique_ordered(phrases)


def preserve_important_versions(short_text: str, deterministic_text: str, context: dict[str, Any]) -> str:
    required = important_short_version_phrases(context)
    if required and any(phrase not in short_text for phrase in required if phrase in deterministic_text):
        return deterministic_text
    return short_text


def short_highlight_terms(context: dict[str, Any]) -> list[str]:
    meta = project_metadata(context)
    terms = [
        normalize_id_value(meta.get("library_kit")),
        normalize_id_value(meta.get("index_kit")),
        normalize_id_value(meta.get("umi")),
        normalize_id_value(meta.get("spike_in")),
        normalize_id_value(meta.get("sequencing_kit")),
    ]
    formatted_assay = format_publication_value("application", meta.get("application"))
    if formatted_assay:
        terms.append(formatted_assay)
    return unique_ordered([term for term in terms if term])


def emphasize_short_technical_terms(short_text: str, context: dict[str, Any]) -> str:
    terms = sorted(short_highlight_terms(context), key=len, reverse=True)
    if not terms:
        return short_text

    references_match = re.search(r"(?ms)\n\nReferences\s*\n", short_text)
    if references_match:
        body = short_text[: references_match.start()]
        tail = short_text[references_match.start() :]
    else:
        body = short_text
        tail = ""

    for term in terms:
        pattern = re.compile(rf"(?<!`){re.escape(term)}(?!`)")
        body = pattern.sub(lambda _: f"`{term}`", body)
    return body + tail


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
            "For the short methods text, produce a clean condensed version of the long methods text, not an unrelated re-summary.",
            "For the short methods text, write compact manuscript prose in 1-2 short paragraphs, followed by a references section.",
            "In the short methods text, preserve exact technical product names and assay-specific terms so they remain visually identifiable.",
            "Follow Nature-style methods guidance: be concise, include the information needed for interpretation and replication, and avoid re-describing standard published methods when a citation suffices.",
            "For the long methods text, it is acceptable to use clear subsection headings such as Relevant Settings, Reference Details, Key Command Parameters, Software, and References, but avoid unnecessary internal headings like Computational Approach when simple detailed bullets read more naturally.",
            "When project-level assay metadata are available, include the crucial sequencing and library-preparation details in a concise publication-appropriate way.",
            "For pipeline-style workflows such as nf-core runs, include the key recorded command parameters and the best available reference details, including genome and annotation version when recoverable from recorded files.",
            "When multiple settings or parameters are relevant, present them as bullet lists instead of dense prose.",
            "Only mention settings that materially affect the analysis or interpretation.",
            "Include the relevant citations and reference items for each workflow step in the long methods text when they are available in the structured context.",
            "Do not shorten, paraphrase, or abbreviate the provided reference text entries. Preserve their wording and include the URL for every reference item that has one.",
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
    short_draft = deterministic_short_methods(context, catalog)
    refs = references_markdown(citation_ids, catalog)
    prompt = build_prompt(context, long_draft, short_draft, refs, args.style)

    response_payload: dict[str, Any] = {
        "used_llm": False,
        "reason": "LLM polishing not used.",
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
                short_draft = str(parsed.get("methods_short") or short_draft)
                refs = str(parsed.get("methods_references") or refs)
                refs = references_markdown(citation_ids, catalog)
                short_draft = replace_references_section(short_draft, numbered_references_markdown(citation_ids, catalog))
                short_draft = preserve_important_versions(short_draft, deterministic_short_methods(context, catalog), context)
                short_draft = emphasize_short_technical_terms(short_draft, context)
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

    short_draft = emphasize_short_technical_terms(short_draft, context)

    write_yaml(results_dir / "methods_context.yaml", context)
    (results_dir / "methods_long.md").write_text(long_draft, encoding="utf-8")
    (results_dir / "methods_short.md").write_text(short_draft, encoding="utf-8")
    (results_dir / "methods_long.html").write_text(render_methods_html(long_draft, "Methods Long"), encoding="utf-8")
    (results_dir / "methods_short.html").write_text(render_methods_html(short_draft, "Methods Short"), encoding="utf-8")
    (results_dir / "methods_references.md").write_text(refs, encoding="utf-8")
    (results_dir / "methods_prompt.md").write_text(prompt, encoding="utf-8")
    write_json(results_dir / "methods_response.json", response_payload)

    print(f"[info] wrote {results_dir / 'methods_context.yaml'}")
    print(f"[info] wrote {results_dir / 'methods_long.md'}")
    print(f"[info] wrote {results_dir / 'methods_short.md'}")
    print(f"[info] wrote {results_dir / 'methods_long.html'}")
    print(f"[info] wrote {results_dir / 'methods_short.html'}")
    print(f"[info] wrote {results_dir / 'methods_references.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
