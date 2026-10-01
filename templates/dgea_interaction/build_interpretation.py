#!/usr/bin/env python3
"""Build an evidence-bound interpretation, optionally polished by an OpenAI-compatible LLM."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

import yaml


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", default="results")
    p.add_argument("--config", default="config/analysis.yaml")
    p.add_argument("--use-llm", default="true")
    p.add_argument("--llm-config", default="")
    p.add_argument("--llm-base-url", default="")
    p.add_argument("--llm-model", default="")
    p.add_argument("--llm-temperature", default="0.2")
    return p.parse_args()


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def integer(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def deterministic(context: dict) -> str:
    summaries = {x["contrast_id"]: x for x in context["contrast_summary"]}
    labels = context["labels"]
    alpha = context["alpha"]
    lfc = context["lfc_threshold"]
    lines = [
        "## Evidence-bound interpretation",
        "",
        "> This section was generated deterministically from the result tables. Statistical interaction results, not differences between two separate DEG-list sizes, determine whether genotype modifies a response.",
        "",
    ]
    order = [
        "baseline_ttn", "wt_sr_vs_control", "ttn_sr_vs_control",
        "ttn_sr_response_interaction", "wt_af_vs_sr", "ttn_af_vs_sr",
        "ttn_af_response_interaction",
    ]
    for cid in order:
        row = summaries.get(cid)
        if not row:
            continue
        hits, fdr = integer(row.get("n_evidence_threshold")), integer(row.get("n_fdr_significant"))
        fdr_label = "gene" if fdr == 1 else "genes"
        lines += [f"### {labels.get(cid, cid)}", "", f"{fdr} {fdr_label} met FDR < {alpha:g}; {hits} also met |shrunken log2FC| ≥ {lfc:g}. "]
        if "interaction" in cid:
            lines[-1] += "This is the direct test of whether the response differs by genotype."
        else:
            lines[-1] += "This comparison is descriptive for its stated genotype/condition and cannot substitute for an interaction test."
        lines.append("")
    lines += [
        "### Where to find response-pattern details", "",
        "Enhanced, reduced/blunted, genotype-specific, and opposite-response classifications are descriptive follow-up summaries of interaction-significant genes. Their definitions, within-genotype effect estimates, and gene-level evidence are presented in the two interaction comparison reports rather than repeated in this overview.", "",
        "### Pathways and limitations", "",
    ]
    for item in context["pathway_status"]:
        if item.get("contrast_id"):
            label = labels.get(item["contrast_id"], item["contrast_id"])
            lines.append(f"- {label}: {item.get('pathways_fdr', '0')} GO biological-process gene sets at the configured FDR threshold.")
        elif item.get("detail"):
            lines.append(f"- {item['detail']}")
    lines += [
        "", "These results are exploratory transcriptomic evidence. Multiple testing, modest sample size, effect uncertainty, annotation coverage, and pathway redundancy should be considered before biological or causal claims are made.", "",
    ]
    return "\n".join(lines)


def settings(a: argparse.Namespace) -> dict:
    config_path = Path(a.llm_config).expanduser() if a.llm_config else None
    if config_path is None and os.getenv("LINKAR_LLM_CONFIG"):
        config_path = Path(os.environ["LINKAR_LLM_CONFIG"]).expanduser()
    config = yaml.safe_load(config_path.read_text()) if config_path and config_path.is_file() else {}
    config = config if isinstance(config, dict) else {}
    key_env = str(config.get("api_key_env") or "")
    api_key = os.getenv("LINKAR_LLM_API_KEY", "") or (os.getenv(key_env, "") if key_env else "") or str(config.get("api_key") or config.get("token") or "")
    return {
        "base_url": a.llm_base_url or os.getenv("LINKAR_LLM_BASE_URL", "") or str(config.get("base_url") or ""),
        "model": a.llm_model or os.getenv("LINKAR_LLM_MODEL", "") or str(config.get("model") or ""),
        "temperature": float(a.llm_temperature or config.get("temperature") or 0.2),
        "api_key": api_key,
        "api_key_source": "LINKAR_LLM_API_KEY" if os.getenv("LINKAR_LLM_API_KEY") else (key_env or ("llm_config" if api_key else "")),
        "config_path": str(config_path or ""),
    }


def call_llm(prompt: str, cfg: dict) -> tuple[str, dict]:
    payload = {"model": cfg["model"], "temperature": cfg["temperature"], "messages": [
        {"role": "system", "content": "You are a cautious RNA-seq analyst. Use only supplied evidence and return valid JSON."},
        {"role": "user", "content": prompt},
    ]}
    request = Request(cfg["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=120) as response:
        raw = json.loads(response.read().decode("utf-8"))
    content = str(raw.get("choices", [{}])[0].get("message", {}).get("content") or "")
    match = re.search(r"\{.*\}", content, re.S)
    parsed = json.loads(match.group(0) if match else content)
    text = str(parsed.get("interpretation_markdown") or "").strip()
    if not text or "interaction" not in text.lower():
        raise ValueError("LLM response lacked a usable interaction interpretation")
    return text + "\n", raw


def main() -> int:
    a = args()
    root, config_path = Path(a.results_dir), Path(a.config)
    config = yaml.safe_load(config_path.read_text())
    payload_path = root / "interpretation_data.json"
    payload = json.loads(payload_path.read_text()) if payload_path.is_file() else {}
    summary = payload.get("contrast_summary") or rows(root / "tables/contrast_summary.csv")
    context = {
        "alpha": float(config["analysis"]["alpha"]),
        "lfc_threshold": float(config["analysis"]["lfc_threshold"]),
        "primary_contrast": config["analysis"]["primary_contrast"],
        "labels": {x["id"]: x["label"] for x in config["contrasts"]},
        "contrast_summary": summary,
        "response_classes": payload.get("response_classes") or rows(root / "tables/response_class_summary.csv"),
        "pathway_status": payload.get("pathway_status") or rows(root / "tables/pathways/status.csv"),
        "leading_genes": payload.get("leading_genes") or {},
    }
    draft = deterministic(context)
    prompt = "\n".join([
        "Write a concise, readable Markdown interpretation of this paired RNA-seq factorial analysis.",
        "Return JSON with exactly one key: interpretation_markdown.",
        "Never infer genotype modification from unequal within-genotype DEG counts; use interaction rows only.",
        "Separate baseline effect, normal-stimulation response, AF-specific response, and genotype-by-condition interactions.",
        "Keep response-class definitions and gene-level classification details in the interaction sub-reports; do not list technical response-class IDs or non-significant-gene counts in the overview interpretation.",
        "Describe pathway evidence only when present. State uncertainty and do not invent mechanisms.",
        "Explicitly say the text is LLM-assisted. Do not include local paths.",
        "Structured evidence:\n" + yaml.safe_dump(context, sort_keys=False, allow_unicode=True),
        "Deterministic fallback:\n" + draft,
    ])
    cfg = settings(a)
    public_cfg = {k: v for k, v in cfg.items() if k != "api_key"}
    response_record: dict = {"used_llm": False, "reason": "LLM disabled or incomplete configuration.", "settings": public_cfg}
    final = draft
    if truthy(a.use_llm) and all(cfg.get(k) for k in ("base_url", "model", "api_key")):
        try:
            final, raw = call_llm(prompt, cfg)
            response_record = {"used_llm": True, "settings": public_cfg, "raw": raw}
        except Exception as exc:
            response_record["reason"] = f"LLM request failed; deterministic fallback used: {exc}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "interpretation_context.yaml").write_text(yaml.safe_dump(context, sort_keys=False, allow_unicode=True))
    (root / "interpretation_draft.md").write_text(draft)
    (root / "interpretation_prompt.md").write_text(prompt)
    (root / "interpretation.md").write_text(final)
    (root / "interpretation_response.json").write_text(json.dumps(response_record, indent=2, ensure_ascii=False) + "\n")
    print("LLM-assisted interpretation written." if response_record["used_llm"] else f"Deterministic interpretation written: {response_record['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
