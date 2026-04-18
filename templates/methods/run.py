#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate project-level methods drafts.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--project-dir", default="..")
    parser.add_argument("--style", default="publication")
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


def deterministic_long_methods(context: dict[str, Any]) -> str:
    lines = ["# Methods", ""]
    project = context.get("project") if isinstance(context.get("project"), dict) else {}
    project_id = str(project.get("id") or "the project")
    lines.append(f"Methods were assembled from the recorded Linkar project history for `{project_id}`.")
    author = str(project.get("author") or "").strip()
    if author:
        lines.append(f"The recorded project author information was: {author}.")
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
        template = str(run.get("template") or "")
        lines.append(f"## {label}")
        catalog = run.get("catalog") if isinstance(run.get("catalog"), dict) else {}
        summary = str(run.get("summary") or "").strip()
        method_core = str(catalog.get("method_core") or "").strip()
        if method_core:
            lines.append(method_core)
        elif summary:
            lines.append(summary)
        for detail in catalog.get("method_details") or []:
            if isinstance(detail, str) and detail.strip():
                lines.append(detail.strip())
        version = str(run.get("version") or "").strip()
        if version:
            lines.append(f"The recorded Linkar template version was `{version}`.")
        params = run.get("params") if isinstance(run.get("params"), dict) else {}
        param_text = format_param_sentence(params)
        if param_text:
            lines.append(f"Key recorded parameters for `{template}` were: {param_text}.")
        interpreted_params = run.get("interpreted_params") if isinstance(run.get("interpreted_params"), list) else []
        if interpreted_params:
            explained = []
            for item in interpreted_params:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                value = str(item.get("value") or "").strip()
                explanation = str(item.get("explanation") or "").strip()
                if name and value and explanation:
                    explained.append(f"{name}={value} ({explanation})")
            if explained:
                lines.append(f"Interpreted run-specific settings included: {'; '.join(explained)}.")
        param_context = catalog.get("param_context") if isinstance(catalog.get("param_context"), list) else []
        for hint in param_context:
            if isinstance(hint, str) and hint.strip():
                lines.append(hint.strip())
        hints = run.get("organism_or_reference") if isinstance(run.get("organism_or_reference"), dict) else {}
        if hints:
            lines.append(f"Organism, genome, or reference context included: {format_param_sentence(hints)}.")
        software_versions = run.get("software_versions")
        if isinstance(software_versions, list) and software_versions:
            rendered_versions = []
            for item in software_versions:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                version = str(item.get("version") or item.get("raw") or "").strip()
                if name and version:
                    rendered_versions.append(f"{name}: {version}")
                elif name:
                    rendered_versions.append(name)
            if rendered_versions:
                lines.append(f"Recorded software and reference versions included: {'; '.join(rendered_versions)}.")
        runtime_command = run.get("runtime_command") if isinstance(run.get("runtime_command"), dict) else {}
        command_pretty = str(runtime_command.get("command_pretty") or "").strip()
        if command_pretty:
            lines.append(f"Recorded execution command: `{command_pretty}`.")
        command_hints = catalog.get("command_hints") if isinstance(catalog.get("command_hints"), list) else []
        for hint in command_hints:
            if isinstance(hint, str) and hint.strip():
                lines.append(hint.strip())
        runtime = run.get("runtime") if isinstance(run.get("runtime"), dict) else {}
        if runtime.get("success") is not None:
            lines.append(f"The recorded runtime success state was `{runtime.get('success')}`.")
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
    text = f"Project `{project_id}` was processed with Linkar using {len(runs)} recorded workflow step(s)"
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
            "Runs marked with publication_relevance=false are operational or administrative context and should normally not appear in the final publication methods narrative unless explicitly needed.",
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
    llm_settings = resolve_llm_settings(args, project_dir)
    context = {
        "project": {
            "id": project_data.get("id") or project_dir.name,
            "path": str(project_dir),
            "author": project_author_text(project_data),
        },
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
    long_draft = deterministic_long_methods(context)
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
