#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml


TEXT_EXTENSIONS = {
    ".r",
    ".rmd",
    ".py",
    ".sh",
    ".bash",
    ".qmd",
    ".md",
    ".txt",
    ".log",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".ipynb",
    ".config",
    ".conf",
    ".ini",
    ".nf",
    ".smk",
}

SKIP_EXTENSIONS = {
    ".fastq",
    ".fq",
    ".bam",
    ".sam",
    ".cram",
    ".bai",
    ".crai",
    ".sra",
    ".h5",
    ".h5ad",
    ".hdf5",
    ".loom",
    ".rds",
    ".rda",
    ".rdata",
    ".parquet",
    ".feather",
    ".zip",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".tar",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".pdf",
    ".docx",
}

SKIP_DIR_NAMES = {
    ".git",
    ".pixi",
    ".renv",
    "renv",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".ipynb_checkpoints",
    ".snakemake",
    ".nextflow",
    ".quarto",
    "node_modules",
    "cache",
    "tmp",
    "temp",
}

MAX_READ_FILES = 250
MAX_FILE_BYTES = 350_000
MAX_EXCERPT_CHARS = 18_000
MAX_PROMPT_CHARS = 180_000

SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd)\b\s*[:=]\s*['\"]?[^'\"\s,;}]+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use an LLM to generate a publication methods docx from input paths.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--input-paths", required=True)
    parser.add_argument("--out-file", default="methods.docx")
    parser.add_argument("--title", default="Methods")
    parser.add_argument("--style", default="publication")
    parser.add_argument("--keep-intermediates", default="false")
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


def parse_input_paths(raw: str) -> list[Path]:
    text = raw.strip()
    values: list[str] = []
    if text.startswith("[") or text.startswith("-"):
        try:
            parsed = yaml.safe_load(text)
            if isinstance(parsed, list):
                values = [str(item) for item in parsed]
        except Exception:
            values = []
    if not values:
        separators = [os.pathsep, "\n", ","]
        values = [text]
        for sep in separators:
            if sep in text:
                values = [part.strip() for part in re.split(rf"{re.escape(sep)}", text) if part.strip()]
                break
    return [Path(value).expanduser().resolve() for value in values if value.strip()]


def redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        def replace(match: re.Match[str]) -> str:
            value = match.group(0)
            if value.lower().startswith("bearer "):
                return "Bearer ***redacted***"
            return value.split(":", 1)[0].split("=", 1)[0] + "=***redacted***"

        redacted = pattern.sub(replace, redacted)
    return redacted


def is_text_candidate(path: Path) -> bool:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if any(suffix in SKIP_EXTENSIONS for suffix in suffixes):
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS


def scan_inputs(input_paths: list[Path]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    read_count = 0

    def add_file(path: Path) -> None:
        nonlocal read_count
        try:
            stat = path.stat()
        except OSError as exc:
            warnings.append(f"Could not stat {path}: {exc}")
            return

        suffixes = [suffix.lower() for suffix in path.suffixes]
        record: dict[str, Any] = {
            "path": str(path),
            "name": path.name,
            "size_bytes": stat.st_size,
            "suffixes": suffixes,
            "included_text": False,
            "skip_reason": "",
        }

        if any(suffix in SKIP_EXTENSIONS for suffix in suffixes):
            record["skip_reason"] = "excluded extension"
        elif not is_text_candidate(path):
            record["skip_reason"] = "not a configured text-like file"
        elif stat.st_size > MAX_FILE_BYTES:
            record["skip_reason"] = f"larger than {MAX_FILE_BYTES} bytes"
        elif read_count >= MAX_READ_FILES:
            record["skip_reason"] = f"text file limit reached ({MAX_READ_FILES})"
        else:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                record["skip_reason"] = f"could not read text: {exc}"
            else:
                text = redact_text(text)
                if path.suffix.lower() in {".html", ".htm"}:
                    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
                    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
                    text = re.sub(r"<[^>]+>", " ", text)
                record["included_text"] = True
                record["text_excerpt"] = compact_excerpt(text)
                read_count += 1

        records.append(record)

    for input_path in input_paths:
        if not input_path.exists():
            warnings.append(f"Input path does not exist: {input_path}")
            continue
        if input_path.is_file():
            add_file(input_path)
            continue

        for root, dirs, files in os.walk(input_path):
            dirs[:] = [name for name in dirs if name not in SKIP_DIR_NAMES and not name.startswith(".")]
            for name in sorted(files):
                add_file(Path(root) / name)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_paths": [str(path) for path in input_paths],
        "warnings": warnings,
        "files_total": len(records),
        "files_with_text": sum(1 for record in records if record["included_text"]),
        "files": records,
    }


def compact_excerpt(text: str) -> str:
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    if len(text) <= MAX_EXCERPT_CHARS:
        return text
    head = text[: MAX_EXCERPT_CHARS // 2]
    tail = text[-MAX_EXCERPT_CHARS // 2 :]
    return f"{head}\n\n[... middle truncated by methods_from_paths ...]\n\n{tail}"


def trim_prompt(prompt: str) -> str:
    if len(prompt) <= MAX_PROMPT_CHARS:
        return prompt
    return prompt[:MAX_PROMPT_CHARS] + "\n\n[Prompt truncated because the collected evidence exceeded the template limit.]\n"


def build_prompt(context: dict[str, Any], title: str, style: str) -> str:
    prompt = f"""
You are drafting the Methods section for an academic publication.

Task:
- Read the supplied file manifest and text excerpts from analysis folders.
- Infer the computational/QC/analysis workflow from the evidence.
- Write one publication-ready Methods document with both:
  1. a concise short version suitable for a manuscript methods subsection
  2. a longer detailed version suitable for internal review or supplement-style methods
- Add important citations for tools, algorithms, databases, pipelines, and benchmark/community guidance that are actually supported by the evidence.
- If the evidence indicates single-cell analysis, align wording with community standards from Single-cell Best Practices (https://www.sc-best-practices.org/) where applicable.
- Do not invent sample counts, thresholds, organisms, reference genomes, software versions, or analysis decisions that are not supported by the provided files.
- When evidence is incomplete, state the uncertainty briefly in the long version instead of guessing.
- Do not mention Linkar, this template, prompt construction, or the scanning process in the final prose.

Requested title: {title}
Style hint: {style}

Return only valid JSON with exactly these string keys:
- methods_short
- methods_long
- references

The final text should be academic prose, not a bullet-only checklist. Use clear section headings in the long version when useful.

Evidence follows as JSON. `included_text=false` files are present in the folder but were not read because they were binary, too large, or not text-like; use their names only as weak context.

{json.dumps(context, indent=2, sort_keys=True)}
"""
    return trim_prompt(prompt.strip() + "\n")


def load_config(path: str) -> dict[str, Any]:
    if not path:
        return {}
    config_path = Path(path).expanduser()
    if not config_path.exists():
        return {}
    try:
        if config_path.suffix.lower() == ".json":
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def resolve_llm_settings(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.llm_config)
    api_key_env = str(config.get("api_key_env") or "LINKAR_LLM_API_KEY")
    return {
        "api_key": os.getenv("LINKAR_LLM_API_KEY") or os.getenv(api_key_env) or str(config.get("api_key") or ""),
        "base_url": args.llm_base_url or os.getenv("LINKAR_LLM_BASE_URL") or str(config.get("base_url") or ""),
        "model": args.llm_model or os.getenv("LINKAR_LLM_MODEL") or str(config.get("model") or ""),
        "temperature": args.llm_temperature if args.llm_temperature is not None else float(config.get("temperature") or 0.2),
    }


def call_llm(prompt: str, settings: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in ("api_key", "base_url", "model") if not settings.get(name)]
    if missing:
        raise SystemExit(f"LLM settings are required for methods_from_paths; missing: {', '.join(missing)}")

    endpoint = str(settings["base_url"]).rstrip("/") + "/chat/completions"
    payload = {
        "model": settings["model"],
        "temperature": settings["temperature"],
        "messages": [
            {"role": "system", "content": "You write accurate academic methods from supplied project evidence."},
            {"role": "user", "content": prompt},
        ],
    }
    req = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=180) as resp:
            response = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise SystemExit(f"LLM request failed: {exc.code} {detail[:1000]}")
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"LLM request failed: {exc}")

    try:
        content = response["choices"][0]["message"]["content"]
    except Exception as exc:
        raise SystemExit(f"LLM response did not contain choices[0].message.content: {exc}")

    parsed = parse_llm_json(content)
    return {"used_llm": True, "parsed": parsed, "raw": response}


def parse_llm_json(content: str) -> dict[str, str]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {"methods_short": "", "methods_long": cleaned, "references": ""}
    if not isinstance(parsed, dict):
        return {"methods_short": "", "methods_long": cleaned, "references": ""}
    return {
        "methods_short": str(parsed.get("methods_short") or "").strip(),
        "methods_long": str(parsed.get("methods_long") or "").strip(),
        "references": str(parsed.get("references") or "").strip(),
    }


def markdown_blocks(markdown_text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for raw in markdown_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append(("heading1", line[2:].strip()))
        elif line.startswith("## "):
            blocks.append(("heading2", line[3:].strip()))
        elif line.startswith("### "):
            blocks.append(("heading3", line[4:].strip()))
        elif re.match(r"^\d+\.\s+", line):
            blocks.append(("list", re.sub(r"^\d+\.\s+", "", line).strip()))
        elif line.startswith("- "):
            blocks.append(("list", line[2:].strip()))
        else:
            blocks.append(("paragraph", line))
    return blocks


def paragraph_xml(text: str, style: str = "paragraph") -> str:
    style_map = {
        "heading1": "Heading1",
        "heading2": "Heading2",
        "heading3": "Heading3",
        "list": "ListParagraph",
    }
    ppr = f'<w:pPr><w:pStyle w:val="{style_map[style]}"/></w:pPr>' if style in style_map else ""
    escaped = html.escape(text, quote=False)
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'


def make_docx(path: Path, title: str, methods_short: str, methods_long: str, references: str) -> None:
    blocks = [("heading1", title), ("heading2", "Short Version")]
    blocks.extend(markdown_blocks(methods_short))
    blocks.append(("heading2", "Long Version"))
    blocks.extend(markdown_blocks(methods_long))
    if references.strip():
        blocks.append(("heading2", "References"))
        blocks.extend(markdown_blocks(references))

    body = "\n".join(paragraph_xml(text, style) for style, text in blocks)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>
"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="720"/></w:pPr></w:style>
</w:styles>
"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", styles_xml)


def resolve_out_file(raw: str, results_dir: Path) -> Path:
    path = Path(raw or "methods.docx").expanduser()
    if not path.is_absolute():
        path = results_dir / path
    return path.resolve()


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).expanduser().resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    input_paths = parse_input_paths(args.input_paths)
    if not input_paths:
        raise SystemExit("input_paths must contain at least one file or directory.")

    context = scan_inputs(input_paths)
    prompt = build_prompt(context, args.title, args.style)
    response = call_llm(prompt, resolve_llm_settings(args))
    parsed = response["parsed"]
    if not parsed["methods_long"] and not parsed["methods_short"]:
        raise SystemExit("LLM response did not include methods_long or methods_short content.")

    out_file = resolve_out_file(args.out_file, results_dir)
    fixed_docx = results_dir / "methods.docx"
    make_docx(out_file, args.title, parsed["methods_short"], parsed["methods_long"], parsed["references"])
    if out_file != fixed_docx:
        shutil.copy2(out_file, fixed_docx)
    (results_dir / "out_file.txt").write_text(str(out_file) + "\n", encoding="utf-8")

    if parse_bool(args.keep_intermediates, False):
        (results_dir / "methods_context.yaml").write_text(yaml.safe_dump(context, sort_keys=False), encoding="utf-8")
        (results_dir / "methods_prompt.md").write_text(prompt, encoding="utf-8")
        (results_dir / "methods_short.md").write_text(parsed["methods_short"] + "\n", encoding="utf-8")
        (results_dir / "methods_long.md").write_text(parsed["methods_long"] + "\n", encoding="utf-8")
        (results_dir / "methods_references.md").write_text(parsed["references"] + "\n", encoding="utf-8")
        (results_dir / "methods_response.json").write_text(json.dumps(response, indent=2, sort_keys=True), encoding="utf-8")

    print(f"[info] scanned {context['files_total']} files; included text from {context['files_with_text']} files")
    print(f"[info] wrote {fixed_docx}")
    if out_file != fixed_docx:
        print(f"[info] wrote {out_file}")
    for warning in context["warnings"]:
        print(f"[warning] {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
