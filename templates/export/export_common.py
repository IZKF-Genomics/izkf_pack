from __future__ import annotations

import glob
import json
import re
import secrets
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExportContext:
    project_dir: Path
    template_dir: Path
    results_dir: Path
    params: dict[str, Any]

    @property
    def project_data(self) -> dict[str, Any]:
        return load_yaml(self.project_dir / "project.yaml")


def normalize_id_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return ""


def resolve_metadata_identifiers(params: dict[str, Any], project_data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"agendo_id": "", "flowcell_id": "", "sources": {}}

    ag_cli = normalize_id_value(params.get("agendo_id"))
    fc_cli = normalize_id_value(params.get("flowcell_id"))
    if ag_cli:
        out["agendo_id"] = ag_cli
        out["sources"]["agendo_id"] = "cli_param"
    if fc_cli:
        out["flowcell_id"] = fc_cli
        out["sources"]["flowcell_id"] = "cli_param"

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


def split_csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value)]


def split_project_path(path_str: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in path_str:
        if ch == "." and depth == 0:
            if buf:
                parts.append("".join(buf))
                buf = []
            continue
        if ch == "[":
            depth += 1
        elif ch == "]" and depth > 0:
            depth -= 1
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def apply_selector(value: Any, selector: str) -> Any:
    if isinstance(value, list):
        if selector.isdigit():
            index = int(selector)
            if 0 <= index < len(value):
                return value[index]
            return None
        if "=" in selector:
            key, expected = selector.split("=", 1)
            for item in value:
                if isinstance(item, dict) and str(item.get(key)) == expected:
                    return item
    return None


def resolve_project_key(project_data: dict[str, Any], path_str: str) -> Any:
    current: Any = project_data
    for part in split_project_path(path_str):
        if "[" in part and part.endswith("]"):
            base, rest = part.split("[", 1)
            selector = rest[:-1]
            if base:
                if not isinstance(current, dict):
                    return None
                current = current.get(base)
            current = apply_selector(current, selector)
        else:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        if current is None:
            return None
    return current


def project_authors(project_data: dict[str, Any]) -> list[str]:
    author = project_data.get("author")
    if isinstance(author, dict):
        name = str(author.get("name") or "").strip()
        org = str(author.get("organization") or "").strip()
        if name and org:
            return [f"{name}, {org}"]
        if name:
            return [name]
    authors = project_data.get("authors") or []
    if not isinstance(authors, list):
        return []
    out: list[str] = []
    for item in authors:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            aff = str(item.get("affiliation") or item.get("organization") or "").strip()
            if name and aff:
                out.append(f"{name}, {aff}")
            elif name:
                out.append(name)
    return out


def derive_export_credentials(project_name: str, params: dict[str, Any]) -> tuple[str, str]:
    username = str(params.get("export_username") or "").strip()
    password = str(params.get("export_password") or "").strip()
    if not username and project_name:
        parts = project_name.split("_")
        if len(parts) >= 2 and parts[1]:
            username = parts[1]
    if not password:
        password = secrets.token_urlsafe(16)
    return username, password


GLOB_CHARS = set("*?[")


def has_glob(path: str) -> bool:
    return any(ch in path for ch in GLOB_CHARS)


def auto_link_name(path: str, dest: str) -> str:
    base = Path(dest).name if path == "." else Path(path).name
    return base.replace("_", " ").strip() if base else ""


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return slug.strip("._-")


def template_placeholders(template_id: str, entry: dict[str, Any]) -> dict[str, str]:
    template_path = str(entry.get("path") or "").strip()
    template_basename = Path(template_path).name if template_path else template_id
    params = entry.get("params")
    params_name = ""
    if isinstance(params, dict):
        raw_name = params.get("name")
        if isinstance(raw_name, str):
            params_name = raw_name.strip()
    template_label = params_name or template_basename
    template_slug = safe_slug(template_label) or safe_slug(template_basename) or template_id
    return {
        "template_id": template_id,
        "template_root": template_path,
        "template_path": template_path,
        "template_basename": template_basename,
        "template_label": template_label,
        "template_slug": template_slug,
        "instance_id": str(entry.get("instance_id") or "").strip(),
    }


def expand_placeholders(value: str, placeholders: dict[str, str]) -> str:
    expanded = value
    for key, replacement in placeholders.items():
        expanded = expanded.replace("{" + key + "}", replacement)
    return expanded


def normalize_path_for_link(resolved: str, src_root: Path) -> str:
    if ":" in resolved:
        host, rest = resolved.split(":", 1)
        if host and rest.startswith("/"):
            resolved = rest
    resolved_path = Path(resolved)
    if resolved_path.is_absolute():
        try:
            return resolved_path.relative_to(src_root).as_posix()
        except ValueError:
            return resolved_path.name
    return resolved


def resolve_report_link_path(item: dict[str, Any], project_data: dict[str, Any], src_root: Path) -> str | None:
    path = item.get("path")
    if isinstance(path, str) and path.strip():
        return path.strip()
    key = item.get("src_project_key")
    if not isinstance(key, str) or not key.strip():
        return None
    resolved = resolve_project_key(project_data, key)
    if not isinstance(resolved, str) or not resolved.strip():
        return None
    return normalize_path_for_link(resolved.strip(), src_root)


def build_report_links(
    entry: dict[str, Any],
    src: Path,
    dest: str,
    project_data: dict[str, Any],
    placeholders: dict[str, str],
) -> list[dict[str, str]]:
    report_links = entry.get("report_links")
    if not isinstance(report_links, list) or not report_links:
        return []
    src_is_file = src.is_file()
    src_root = src.parent if src_is_file else src
    src_anchor = src if src_is_file else src_root
    links: list[dict[str, str]] = []
    for item in report_links:
        if not isinstance(item, dict):
            continue
        path = resolve_report_link_path(item, project_data, src_root)
        if not isinstance(path, str) or not path:
            continue
        path = expand_placeholders(path, placeholders)
        section = item.get("section")
        if not isinstance(section, str) or not section.strip():
            continue
        section = expand_placeholders(section.strip(), placeholders)
        description = item.get("description")
        if not isinstance(description, str):
            description = ""
        else:
            description = expand_placeholders(description, placeholders)
        link_name = item.get("link_name")
        if not isinstance(link_name, str):
            link_name = ""
        else:
            link_name = expand_placeholders(link_name, placeholders)

        if has_glob(path):
            matches = sorted(Path(p) for p in glob.glob(str(src_root / path), recursive=True))
            for match in matches:
                if not match.exists():
                    continue
                try:
                    rel_path = match.relative_to(src_root).as_posix()
                except ValueError:
                    rel_path = match.name
                link = {"path": rel_path, "section": section}
                if description:
                    link["description"] = description
                name = link_name or auto_link_name(match.name, dest)
                if name:
                    link["link_name"] = name
                links.append(link)
            continue

        target = src_anchor if path == "." else src_root / path
        if not target.exists():
            continue
        link = {"path": "." if path == "." else path, "section": section}
        if description:
            link["description"] = description
        name = link_name or auto_link_name(path, dest)
        if name:
            link["link_name"] = name
        links.append(link)
    return links


def load_mapping_table(template_dir: Path) -> list[dict[str, Any]]:
    table = load_yaml(template_dir / "export_mapping.table.yaml")
    mappings = table.get("mappings") or []
    if not isinstance(mappings, list):
        raise ValueError("export_mapping.table.yaml must contain a 'mappings' list")
    return [entry for entry in mappings if isinstance(entry, dict)]


def dedupe_template_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for entry in entries:
        template_id = str(entry.get("id") or entry.get("source_template") or "").strip()
        path = str(entry.get("path") or "").strip()
        key = (template_id, path)
        if key not in latest_by_key:
            order.append(key)
        latest_by_key[key] = entry
    return [latest_by_key[key] for key in order]


def build_export_list(project_dir: Path, project_data: dict[str, Any], template_dir: Path) -> list[dict[str, Any]]:
    mappings = load_mapping_table(template_dir)
    template_entries = dedupe_template_entries(
        [entry for entry in project_data.get("templates") or [] if isinstance(entry, dict)]
    )
    export_list: list[dict[str, Any]] = []
    default_host = socket.gethostname()
    for mapping in mappings:
        template_id = mapping.get("template_id")
        if not isinstance(template_id, str) or not template_id or template_id == "export":
            continue
        matches = [
            entry
            for entry in template_entries
            if entry.get("id") == template_id or entry.get("source_template") == template_id
        ]
        for entry in matches:
            placeholders = template_placeholders(template_id, entry)
            src = mapping.get("src")
            if not isinstance(src, str) or not src.strip():
                continue
            template_path = entry.get("path")
            if not isinstance(template_path, str) or not template_path.strip():
                continue
            src = expand_placeholders(src, placeholders)
            project_key = mapping.get("src_project_key")
            if isinstance(project_key, str) and project_key.strip():
                resolved = resolve_project_key(project_data, project_key)
                if isinstance(resolved, str) and resolved.strip():
                    src = resolved.strip()
            src_path = Path(src).expanduser()
            if not src_path.is_absolute():
                src_path = (project_dir / src_path).resolve()
            if not src_path.exists():
                continue
            dest = expand_placeholders(str(mapping.get("dest") or ""), placeholders)
            if not dest:
                continue
            export_entry: dict[str, Any] = {
                "src": str(src_path),
                "dest": dest,
                "host": expand_placeholders(str(mapping.get("host") or default_host), placeholders),
                "project": expand_placeholders(
                    str(mapping.get("project") or project_data.get("id") or project_dir.name),
                    placeholders,
                ),
                "mode": expand_placeholders(str(mapping.get("mode") or "symlink"), placeholders),
            }
            report_links = build_report_links(mapping, src_path, dest, project_data, placeholders)
            if report_links:
                export_entry["report_links"] = report_links
            export_list.append(export_entry)
    return export_list


def mock_metadata_payload(ids: dict[str, str]) -> dict[str, Any]:
    return {
        "ProjectOutput": {
            "application": "unknown",
            "umi": "unknown",
            "spike_in": "unknown",
            "library_kit": "unknown",
            "index_kit": "unknown",
            "sequencer": "unknown",
            "sequencing_kit": "unknown",
            "read_type": "unknown",
            "run_date": None,
            "run_name": None,
            "flow_cell": ids.get("flowcell_id") or None,
            "agendo_id": int(ids["agendo_id"]) if ids.get("agendo_id", "").isdigit() else ids.get("agendo_id") or None,
            "organism": "unknown",
        },
        "RunMetadataDB": {
            "flowcell": ids.get("flowcell_id") or None,
            "paired": None,
            "read1_cycles": None,
            "index1_cycles": None,
            "index2_cycles": None,
            "read2_cycles": None,
        },
        "PredictionConfidence": None,
    }


def load_file_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"metadata_file not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise ValueError(f"metadata_file is empty: {path}")
    if path.suffix.lower() in (".yaml", ".yml"):
        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("metadata payload must be a JSON/YAML object")
    return raw


def fetch_api_payload(base_url: str, endpoint: str, ids: dict[str, str], timeout: int) -> dict[str, Any]:
    base = base_url.strip().rstrip("/")
    if not base:
        raise ValueError("metadata_api_url is empty")
    ep = (endpoint or "/project-output").strip()
    if not ep.startswith("/"):
        ep = "/" + ep
    params = {}
    if ids.get("agendo_id"):
        params["agendo_id"] = ids["agendo_id"]
    if ids.get("flowcell_id"):
        params["flowcell_id"] = ids["flowcell_id"]
    query = f"?{urlencode(params)}" if params else ""
    url = f"{base}{ep}{query}"
    req = Request(url=url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body) if body else {}
    if not isinstance(data, dict):
        raise ValueError("API metadata response is not a JSON object")
    return data


def normalize_metadata_payload(raw: dict[str, Any], ids: dict[str, str], mode_used: str) -> dict[str, Any]:
    po = raw.get("ProjectOutput") if isinstance(raw.get("ProjectOutput"), dict) else {}
    rm = raw.get("RunMetadataDB") if isinstance(raw.get("RunMetadataDB"), dict) else {}
    return {
        "source": {
            "provider": "genomics_api",
            "mode": mode_used,
            "fetched_at": now_utc(),
            "prediction_confidence": raw.get("PredictionConfidence"),
        },
        "identifiers": {
            "agendo_id": po.get("agendo_id") or ids.get("agendo_id") or None,
            "flowcell_id": po.get("flow_cell") or rm.get("flowcell") or ids.get("flowcell_id") or None,
            "run_name": po.get("run_name") or rm.get("project_name") or None,
            "run_project_name": rm.get("project_name"),
            "agendo_link": po.get("agendo_link"),
        },
        "protocol": {
            "application": po.get("application"),
            "agendo_application": po.get("agendo_application"),
            "sciebo_application": po.get("sciebo_application"),
            "library_kit": po.get("library_kit"),
            "index_kit": po.get("index_kit"),
            "umi": po.get("umi"),
            "spike_in": po.get("spike_in"),
            "organism": po.get("organism"),
        },
        "sequencing": {
            "platform": po.get("sequencer"),
            "instrument": rm.get("instrument"),
            "sequencing_kit": po.get("sequencing_kit") or rm.get("seq_kit"),
            "read_type": po.get("read_type"),
            "paired": rm.get("paired"),
            "cycles": {
                "read1": po.get("cycles_read1") or rm.get("read1_cycles"),
                "index1": po.get("cycles_index1") or rm.get("index1_cycles"),
                "index2": po.get("cycles_index2") or rm.get("index2_cycles"),
                "read2": po.get("cycles_read2") or rm.get("read2_cycles"),
            },
            "run_date": po.get("run_date") or rm.get("date"),
            "operator": po.get("operator"),
        },
        "project": {
            "project_ref": po.get("ref") or po.get("project"),
            "provider_name": po.get("provider"),
            "sample_number": po.get("sample_number"),
            "status": po.get("status"),
            "created_by_name": po.get("created_by_name"),
            "created_by_email": po.get("created_by_email"),
            "group_name": po.get("group_name") or po.get("group_"),
            "institute_name": po.get("institute_name"),
            "pi_name": po.get("pi_name"),
            "pi_email": po.get("pi_email"),
        },
    }


def generate_methods_markdown(project_dir: Path, style: str) -> tuple[str, int, int]:
    try:
        from bpm.core import agent_methods

        result = agent_methods.generate_methods_markdown(project_dir, style=style)
        return result.markdown, int(result.templates_count), int(result.citation_count)
    except Exception as exc:
        note = (
            "# Methods Draft\n\n"
            f"Automatic generation failed: {exc}\n"
            "Regenerate manually after installing BPM methods support.\n"
        )
        return note, 0, 0


def extract_citations(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and stripped.lower() == "## citations":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section and stripped.startswith("- "):
            out.append(stripped[2:].strip())
    return out
