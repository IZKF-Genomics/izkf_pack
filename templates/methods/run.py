#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
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


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


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


def read_runtime_summary(run_dir: Path | None) -> dict[str, Any]:
    if run_dir is None:
        return {}
    runtime = read_json(run_dir / ".linkar" / "runtime.json")
    return compact_mapping(
        runtime,
        keys=["command", "cwd", "returncode", "success", "started_at", "finished_at", "duration_seconds"],
    )


def resolve_output_path(project_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (project_dir / path).resolve()
    return path


def load_software_versions(project_dir: Path, outputs: dict[str, Any]) -> list[dict[str, Any]]:
    versions: list[dict[str, Any]] = []
    software_path = resolve_output_path(project_dir, outputs.get("software_versions"))
    if software_path is not None and software_path.exists():
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


def collect_run_context(
    project_dir: Path,
    project_data: dict[str, Any],
    catalog: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    templates_catalog = catalog.get("templates") if isinstance(catalog.get("templates"), dict) else {}
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
        hint = templates_catalog.get(template_id) if isinstance(templates_catalog, dict) else {}
        important_params = hint.get("important_params") if isinstance(hint, dict) else None
        if not isinstance(important_params, list):
            important_params = None
        run_dir = resolve_run_dir(project_dir, entry)
        citations = hint.get("citations") if isinstance(hint, dict) else []
        if not isinstance(citations, list):
            citations = []
        citation_ids.extend(str(item) for item in citations if str(item).strip())
        runs.append(
            {
                "order": index,
                "template": template_id,
                "version": entry.get("template_version"),
                "instance_id": entry.get("instance_id"),
                "label": hint.get("label") if isinstance(hint, dict) else None,
                "summary": hint.get("summary") if isinstance(hint, dict) else None,
                "tools": hint.get("tools") if isinstance(hint, dict) else [],
                "params": compact_mapping(params, keys=important_params),
                "organism_or_reference": infer_organism_or_reference(params),
                "software_versions": load_software_versions(project_dir, outputs),
                "outputs": summarize_outputs(outputs),
                "runtime": read_runtime_summary(run_dir),
                "citations": citations,
            }
        )
    return runs, sorted(set(citation_ids))


def summarize_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in outputs.items():
        if isinstance(value, list):
            summary[key] = {"count": len(value), "examples": value[:3]}
        elif value not in ("", None):
            summary[key] = value
    return summary


def format_param_sentence(params: dict[str, Any]) -> str:
    if not params:
        return ""
    parts = []
    for key, value in params.items():
        if isinstance(value, (list, dict)):
            rendered = json.dumps(value, sort_keys=True)
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    return "; ".join(parts)


def deterministic_long_methods(context: dict[str, Any]) -> str:
    lines = ["# Methods", ""]
    project = context.get("project") if isinstance(context.get("project"), dict) else {}
    project_id = str(project.get("id") or "the project")
    lines.append(f"Methods were generated from the recorded Linkar project history for `{project_id}`.")
    author = str(project.get("author") or "").strip()
    if author:
        lines.append(f"The recorded project author information was: {author}.")
    lines.append("")
    for run in context.get("runs") or []:
        if not isinstance(run, dict):
            continue
        label = str(run.get("label") or run.get("template") or "Workflow step")
        template = str(run.get("template") or "")
        lines.append(f"## {label}")
        summary = str(run.get("summary") or "").strip()
        if summary:
            lines.append(summary)
        version = str(run.get("version") or "").strip()
        if version:
            lines.append(f"The recorded Linkar template version was `{version}`.")
        params = run.get("params") if isinstance(run.get("params"), dict) else {}
        param_text = format_param_sentence(params)
        if param_text:
            lines.append(f"Key recorded parameters for `{template}` were: {param_text}.")
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
        runtime = run.get("runtime") if isinstance(run.get("runtime"), dict) else {}
        if runtime.get("success") is not None:
            lines.append(f"The recorded runtime success state was `{runtime.get('success')}`.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def deterministic_short_methods(context: dict[str, Any]) -> str:
    runs = [run for run in context.get("runs") or [] if isinstance(run, dict)]
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
            "Use the structured context as the source of truth. Do not invent tools, organisms, references, or parameters.",
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
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(extract_json_object(content))
    except Exception:
        parsed = {"methods_long": content, "methods_short": "", "methods_references": ""}
    return {"raw": raw, "parsed": parsed}


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
    context = {
        "project": {
            "id": project_data.get("id") or project_dir.name,
            "path": str(project_dir),
            "author": project_author_text(project_data),
        },
        "style": args.style,
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
    }
    if parse_bool(args.use_llm):
        base_url = args.llm_base_url.strip() or os.environ.get("LINKAR_LLM_BASE_URL", "").strip()
        model = args.llm_model.strip() or os.environ.get("LINKAR_LLM_MODEL", "").strip()
        api_key = os.environ.get("LINKAR_LLM_API_KEY", "").strip()
        if base_url and model and api_key:
            try:
                response_payload = call_openai_compatible_api(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    temperature=args.llm_temperature,
                    prompt=prompt,
                )
                response_payload["used_llm"] = True
                parsed = response_payload.get("parsed") if isinstance(response_payload.get("parsed"), dict) else {}
                long_draft = str(parsed.get("methods_long") or long_draft)
                short_draft = str(parsed.get("methods_short") or short_draft)
                refs = str(parsed.get("methods_references") or refs)
            except Exception as exc:
                response_payload = {
                    "used_llm": False,
                    "reason": f"LLM polishing failed: {exc}",
                }
        else:
            response_payload = {
                "used_llm": False,
                "reason": "LLM polishing requested but LINKAR_LLM_API_KEY, base URL, or model was missing.",
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
