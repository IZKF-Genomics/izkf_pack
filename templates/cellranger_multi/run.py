#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


REFERENCE_MAP = {
    "GRCh38": "/data/shared/10xGenomics/refs/refdata-gex-GRCh38-2024-A",
    "GRCm39": "/data/shared/10xGenomics/refs/refdata-gex-GRCm39-2024-A",
    "mRatBN7.2": "/data/shared/10xGenomics/refs/refdata-gex-mRatBN7-2-2024-A",
    "GRCz11": "/data/shared/10xGenomics/refs/refdata-gex-GRCz11-ensembl115-2026-A",
    "GRCg7b": "/data/shared/10xGenomics/refs/refdata-gex-GRCg7b-ensembl115-2026-A",
}
SAMPLE_FIELDS = ["sample", "gex_fastq_id", "gex_fastqs", "feature_fastq_id", "feature_fastqs", "feature_types"]
FEATURE_FIELDS = ["id", "name", "read", "pattern", "sequence", "feature_type"]
ASSIGNMENT_FIELDS = ["gem_well", "sample_id", "hashtag_ids"]
ALLOWED_FEATURE_TYPES = {
    "Antibody Capture",
    "CRISPR Guide Capture",
    "Multiplexing Capture",
    "Antigen Capture",
}
CELLRANGER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FEATURE_ID_RE = re.compile(r'^[^\s/,\"]+$')
DNA_RE = re.compile(r"^[ACGT]+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render or execute the izkf_pack Cell Ranger multi workspace.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render = subparsers.add_parser("render")
    render.add_argument("--samplesheet", required=True)
    render.add_argument("--genome", default="")
    render.add_argument("--reference", default="")
    render.add_argument("--cellranger-bin", default="cellranger")
    render.add_argument("--localcores", type=int, default=0)
    render.add_argument("--localmem", type=int, default=0)

    execute = subparsers.add_parser("execute")
    execute.add_argument("--workspace", default=".")
    execute.add_argument("--results-dir", default="results")
    execute.add_argument("--prepare-only", action="store_true")
    return parser.parse_args()


def toml_string(value: object) -> str:
    return json.dumps(str(value))


def resolve_reference(genome: str, explicit: str, *, allow_placeholder: bool) -> str:
    if explicit.strip():
        if explicit.strip().startswith("__EDIT_ME_"):
            if allow_placeholder:
                return explicit.strip()
            raise SystemExit(
                "[error] transcriptome reference is unresolved. Edit [reference] in "
                "config/cellranger_multi.toml before running."
            )
        path = Path(explicit).expanduser().resolve()
        if not path.exists() and not allow_placeholder:
            raise SystemExit(f"[error] Cell Ranger transcriptome reference does not exist: {path}")
        return str(path)
    mapped = REFERENCE_MAP.get(genome.strip(), "")
    if mapped and Path(mapped).exists():
        return mapped
    if allow_placeholder:
        return "__EDIT_ME_TRANSCRIPTOME_REFERENCE__"
    if mapped:
        raise SystemExit(f"[error] facility Cell Ranger reference does not exist: {mapped}")
    raise SystemExit(
        "[error] transcriptome reference is unresolved. Edit [reference] in "
        "config/cellranger_multi.toml before running."
    )


def stage_samplesheet(source: Path, destination: Path) -> None:
    if not source.exists():
        raise SystemExit(f"[error] samplesheet was not found: {source}")
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(SAMPLE_FIELDS).difference(reader.fieldnames or []))
        if missing:
            raise SystemExit(f"[error] samplesheet is missing columns: {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        raise SystemExit("[error] samplesheet contains no samples")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_settings(
    destination: Path,
    *,
    genome: str,
    reference: str,
    cellranger_bin: str,
    localcores: int,
    localmem: int,
) -> None:
    resolved_genome = genome.strip() or "__EDIT_ME_GENOME__"
    text = f'''[reference]
# GEX requires a Cell Ranger transcriptome reference. A facility genome label
# is kept for provenance; transcriptome is the value passed to Cell Ranger.
genome = {toml_string(resolved_genome)}
transcriptome = {toml_string(reference)}

[gene_expression]
# Cell Ranger 10 requires this choice explicitly.
create_bam = true

[feature]
# Choose "catalog", "file", or "none" after rendering.
# Catalog IDs are listed in catalogs/manifest.tsv.
source = "__EDIT_ME__"
catalog = ""
file = "config/custom_feature_reference.csv"

[sample_assignment]
# Optional antibody-hashing assignments. Leave file empty for singleplex runs.
# The CSV columns are: gem_well,sample_id,hashtag_ids
file = "config/sample_assignments.csv"

[runtime]
cellranger_bin = {toml_string(cellranger_bin)}
localcores = {max(0, localcores)}
localmem = {max(0, localmem)}
'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def render_workspace(args: argparse.Namespace) -> int:
    workspace = Path.cwd().resolve()
    reference = resolve_reference(args.genome, args.reference, allow_placeholder=True)
    stage_samplesheet(Path(args.samplesheet).expanduser().resolve(), workspace / "config" / "samples.csv")
    write_settings(
        workspace / "config" / "cellranger_multi.toml",
        genome=args.genome,
        reference=reference,
        cellranger_bin=args.cellranger_bin,
        localcores=args.localcores,
        localmem=args.localmem,
    )
    (workspace / "generated" / "multi").mkdir(parents=True, exist_ok=True)
    (workspace / "results").mkdir(parents=True, exist_ok=True)
    print(f"[info] rendered {workspace}")
    print("[next] edit config/cellranger_multi.toml and choose a Feature Reference source")
    print("[next] run ./run.sh")
    return 0


def load_toml(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(f"[error] settings file was not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def resolve_workspace_path(workspace: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (workspace / path).resolve()


def load_catalog_manifest(workspace: Path) -> dict[str, dict[str, str]]:
    path = workspace / "catalogs" / "manifest.tsv"
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["catalog_id"]: row for row in csv.DictReader(handle, delimiter="\t")}


def load_feature_rows(path: Path, *, delimiter: str = ",") -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise SystemExit(f"[error] Feature Reference was not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fields = list(reader.fieldnames or [])
        missing = sorted(set(FEATURE_FIELDS).difference(fields))
        if missing:
            raise SystemExit(f"[error] Feature Reference is missing columns: {', '.join(missing)}")
        rows = [{key: str(value or "").strip() for key, value in row.items()} for row in reader]
    return fields, rows


def validate_feature_rows(rows: list[dict[str, str]], source: Path) -> None:
    if not rows:
        raise SystemExit(f"[error] Feature Reference contains no feature rows: {source}")
    ids: dict[str, int] = {}
    signatures: dict[tuple[str, str, str], str] = {}
    sequences: list[str] = []
    for number, row in enumerate(rows, start=2):
        feature_id = row["id"]
        name = row["name"]
        read = row["read"]
        pattern = row["pattern"]
        sequence = row["sequence"].upper()
        feature_type = row["feature_type"]
        row["sequence"] = sequence
        cellranger_values = [row.get(field, "") for field in FEATURE_FIELDS]
        cellranger_values.extend(row.get(field, "") for field in ("target_gene_id", "target_gene_name", "mhc_allele"))
        try:
            "".join(cellranger_values).encode("ascii")
        except UnicodeEncodeError:
            raise SystemExit(f"[error] non-ASCII value in {source}:{number}") from None
        if not feature_id or not FEATURE_ID_RE.fullmatch(feature_id):
            raise SystemExit(f"[error] invalid feature id in {source}:{number}: {feature_id!r}")
        if not name or any(char in name for char in '/,\"') or any(char.isspace() for char in name):
            raise SystemExit(f"[error] invalid feature name in {source}:{number}: {name!r}")
        if read not in {"R1", "R2"}:
            raise SystemExit(f"[error] read must be R1 or R2 in {source}:{number}")
        if pattern.count("(BC)") != 1:
            raise SystemExit(f"[error] pattern must contain exactly one (BC) in {source}:{number}")
        if not DNA_RE.fullmatch(sequence):
            raise SystemExit(f"[error] sequence must contain only A/C/G/T in {source}:{number}")
        if feature_type not in ALLOWED_FEATURE_TYPES:
            raise SystemExit(f"[error] unsupported feature_type in {source}:{number}: {feature_type}")
        if feature_id in ids:
            raise SystemExit(f"[error] duplicate feature id {feature_id!r} in {source}:{ids[feature_id]} and :{number}")
        ids[feature_id] = number
        signature = (read, pattern, sequence)
        previous = signatures.get(signature)
        if previous is not None:
            raise SystemExit(
                f"[error] duplicate barcode signature for {previous!r} and {feature_id!r} in {source}"
            )
        signatures[signature] = feature_id
        sequences.append(sequence)

    close_pairs = 0
    for index, left in enumerate(sequences):
        for right in sequences[index + 1 :]:
            if len(left) == len(right) and sum(a != b for a, b in zip(left, right)) <= 1:
                close_pairs += 1
    if close_pairs:
        print(
            f"[warning] Feature Reference contains {close_pairs} barcode pair(s) at Hamming distance <= 1; "
            "review one-mismatch correction risk.",
            file=sys.stderr,
        )


def compile_feature_reference(
    workspace: Path, settings: dict[str, object]
) -> tuple[Path | None, set[str], dict[str, str], str]:
    feature = settings.get("feature") or {}
    if not isinstance(feature, dict):
        raise SystemExit("[error] [feature] must be a TOML table")
    source = os.getenv("FEATURE_SOURCE", str(feature.get("source") or "")).strip().lower()
    env_reference = os.getenv("FEATURE_REFERENCE", "").strip()
    env_catalog = os.getenv("FEATURE_CATALOG", "").strip()
    if env_reference and env_catalog:
        raise SystemExit("[error] set only one of FEATURE_REFERENCE or FEATURE_CATALOG")
    if env_reference:
        source = "file"
    elif env_catalog:
        source = "catalog"
    if source.startswith("__edit_me") or source not in {"catalog", "file", "none"}:
        raise SystemExit(
            "[error] Feature Reference has not been configured. Edit [feature] in "
            "config/cellranger_multi.toml; see FEATURE_REFERENCES.md."
        )
    if source == "none":
        return None, set(), {}, "none"

    if source == "catalog":
        catalog_id = env_catalog or str(feature.get("catalog") or "").strip()
        manifest = load_catalog_manifest(workspace)
        if catalog_id not in manifest:
            available = ", ".join(sorted(manifest)) or "none"
            raise SystemExit(f"[error] unknown catalog {catalog_id!r}. Available catalogs: {available}")
        source_path = workspace / "catalogs" / manifest[catalog_id]["file"]
        fields, rows = load_feature_rows(source_path, delimiter="\t")
        provenance = f"catalog:{catalog_id}"
    else:
        value = env_reference or str(feature.get("file") or "").strip()
        if not value:
            raise SystemExit("[error] feature.source=file requires feature.file or FEATURE_REFERENCE")
        source_path = resolve_workspace_path(workspace, value)
        fields, rows = load_feature_rows(source_path)
        provenance = f"file:{source_path}"

    validate_feature_rows(rows, source_path)
    optional = [field for field in fields if field not in FEATURE_FIELDS and field in {"target_gene_id", "target_gene_name", "mhc_allele"}]
    output_fields = FEATURE_FIELDS + optional
    output_path = workspace / "generated" / "feature_reference.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return output_path, {row["feature_type"] for row in rows}, {
        row["id"]: row["feature_type"] for row in rows
    }, provenance


def load_samples(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(SAMPLE_FIELDS).difference(reader.fieldnames or []))
        if missing:
            raise SystemExit(f"[error] config/samples.csv is missing columns: {', '.join(missing)}")
        rows = [{key: str(value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        raise SystemExit("[error] config/samples.csv contains no rows")
    for row in rows:
        if not CELLRANGER_ID_RE.fullmatch(row["sample"]):
            raise SystemExit(f"[error] invalid Cell Ranger sample id: {row['sample']!r}")
        if not row["gex_fastq_id"] or not Path(row["gex_fastqs"]).is_dir():
            raise SystemExit(f"[error] invalid GEX input for sample {row['sample']}")
        if row["feature_fastq_id"] and not Path(row["feature_fastqs"]).is_dir():
            raise SystemExit(f"[error] invalid Feature Barcode FASTQ directory for sample {row['sample']}")
    return rows


def load_sample_assignments(
    workspace: Path,
    settings: dict[str, object],
    samples: list[dict[str, str]],
    feature_id_types: dict[str, str],
) -> dict[str, list[dict[str, str]]]:
    assignment_settings = settings.get("sample_assignment") or {}
    if not isinstance(assignment_settings, dict):
        raise SystemExit("[error] [sample_assignment] must be a TOML table")
    value = os.getenv(
        "SAMPLE_ASSIGNMENTS",
        str(assignment_settings.get("file") or ""),
    ).strip()
    if not value:
        return {}
    path = resolve_workspace_path(workspace, value)
    if not path.exists():
        raise SystemExit(f"[error] sample assignment file was not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(ASSIGNMENT_FIELDS).difference(reader.fieldnames or []))
        if missing:
            raise SystemExit(f"[error] sample assignment file is missing columns: {', '.join(missing)}")
        rows = [{key: str(value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        return {}

    gem_wells = {row["sample"] for row in samples}
    assignments: dict[str, list[dict[str, str]]] = {}
    assigned_tags: dict[str, set[str]] = {}
    assigned_samples: dict[str, set[str]] = {}
    for number, row in enumerate(rows, start=2):
        gem_well = row["gem_well"]
        sample_id = row["sample_id"]
        hashtag_ids = [item.strip() for item in row["hashtag_ids"].split("|") if item.strip()]
        if gem_well not in gem_wells:
            raise SystemExit(f"[error] unknown gem_well in {path}:{number}: {gem_well!r}")
        if not CELLRANGER_ID_RE.fullmatch(sample_id):
            raise SystemExit(f"[error] invalid sample_id in {path}:{number}: {sample_id!r}")
        if not hashtag_ids:
            raise SystemExit(f"[error] hashtag_ids is empty in {path}:{number}")
        if sample_id in assigned_samples.setdefault(gem_well, set()):
            raise SystemExit(f"[error] duplicate sample_id {sample_id!r} for {gem_well!r} in {path}")
        assigned_samples[gem_well].add(sample_id)
        for hashtag_id in hashtag_ids:
            feature_type = feature_id_types.get(hashtag_id)
            if feature_type is None:
                raise SystemExit(
                    f"[error] hashtag_id {hashtag_id!r} in {path}:{number} is absent from the Feature Reference"
                )
            if feature_type != "Antibody Capture":
                raise SystemExit(
                    f"[error] hashtag_id {hashtag_id!r} in {path}:{number} must have "
                    f"feature_type 'Antibody Capture', found {feature_type!r}"
                )
            if hashtag_id in assigned_tags.setdefault(gem_well, set()):
                raise SystemExit(
                    f"[error] hashtag_id {hashtag_id!r} is assigned more than once for {gem_well!r} in {path}"
                )
            assigned_tags[gem_well].add(hashtag_id)
        assignments.setdefault(gem_well, []).append(
            {"sample_id": sample_id, "hashtag_ids": "|".join(hashtag_ids)}
        )
    return assignments


def write_multi_config(
    path: Path,
    *,
    sample: dict[str, str],
    reference: str,
    create_bam: bool,
    feature_reference: Path | None,
    assignments: list[dict[str, str]],
) -> None:
    rows = [
        ["[gene-expression]"],
        ["reference", reference],
        ["create-bam", str(create_bam).lower()],
        [],
    ]
    if feature_reference is not None:
        rows.extend([["[feature]"], ["reference", str(feature_reference)], []])
    rows.extend([["[libraries]"], ["fastq_id", "fastqs", "feature_types"]])
    rows.append([sample["gex_fastq_id"], sample["gex_fastqs"], "Gene Expression"])
    if sample["feature_fastq_id"]:
        rows.append([sample["feature_fastq_id"], sample["feature_fastqs"], sample["feature_types"]])
    if assignments:
        rows.extend([[], ["[samples]"], ["sample_id", "hashtag_ids"]])
        rows.extend([[row["sample_id"], row["hashtag_ids"]] for row in assignments])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)


def resolve_binary(value: str) -> str:
    if "/" in value:
        path = Path(value).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise SystemExit(f"[error] Cell Ranger executable is invalid: {path}")
        return str(path)
    resolved = shutil.which(value)
    if resolved is None:
        raise SystemExit(f"[error] Cell Ranger executable was not found on PATH: {value}")
    return resolved


def execute_workspace(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    results_dir = Path(args.results_dir).expanduser().resolve()
    settings = load_toml(workspace / "config" / "cellranger_multi.toml")
    reference_settings = settings.get("reference") or {}
    gene_expression_settings = settings.get("gene_expression") or {}
    runtime = settings.get("runtime") or {}
    if not all(isinstance(item, dict) for item in (reference_settings, gene_expression_settings, runtime)):
        raise SystemExit("[error] [reference], [gene_expression], and [runtime] must be TOML tables")
    genome = str(reference_settings.get("genome") or "").strip()
    reference = resolve_reference(
        "" if genome.startswith("__EDIT_ME_") else genome,
        str(reference_settings.get("transcriptome") or ""),
        allow_placeholder=False,
    )
    feature_reference, reference_types, feature_id_types, feature_provenance = compile_feature_reference(
        workspace, settings
    )
    samples = load_samples(workspace / "config" / "samples.csv")
    has_feature_libraries = any(row["feature_fastq_id"] for row in samples)
    if has_feature_libraries and feature_reference is None:
        raise SystemExit("[error] samples.csv contains Feature Barcode libraries but feature.source=none")
    sample_types = {row["feature_types"] for row in samples if row["feature_fastq_id"]}
    if feature_reference is not None and not sample_types.intersection(reference_types):
        raise SystemExit(
            "[error] feature_types in samples.csv do not match feature_type values in the Feature Reference: "
            f"samples={sorted(sample_types)}, reference={sorted(reference_types)}"
        )
    assignments = load_sample_assignments(workspace, settings, samples, feature_id_types)
    create_bam = bool(gene_expression_settings.get("create_bam", True))

    configs: dict[str, Path] = {}
    for sample in samples:
        config_path = workspace / "generated" / "multi" / f"{sample['sample']}.csv"
        write_multi_config(
            config_path,
            sample=sample,
            reference=reference,
            create_bam=create_bam,
            feature_reference=feature_reference,
            assignments=assignments.get(sample["sample"], []),
        )
        configs[sample["sample"]] = config_path

    cellranger = resolve_binary(str(runtime.get("cellranger_bin") or "cellranger"))
    localcores = max(0, int(runtime.get("localcores") or 0))
    localmem = max(0, int(runtime.get("localmem") or 0))
    commands: list[list[str]] = []
    for sample, config_path in configs.items():
        command = [cellranger, "multi", f"--id={sample}", f"--csv={config_path}"]
        if localcores:
            command.append(f"--localcores={localcores}")
        if localmem:
            command.append(f"--localmem={localmem}")
        commands.append(command)

    results_dir.mkdir(parents=True, exist_ok=True)
    runtime_payload = {
        "template": "cellranger_multi",
        "engine": "cellranger multi",
        "reference": reference,
        "feature_reference": feature_provenance,
        "commands": commands,
        "samples": sorted(configs),
        "sample_assignments": {
            gem_well: [row["sample_id"] for row in rows]
            for gem_well, rows in sorted(assignments.items())
        },
    }
    (results_dir / "runtime_command.json").write_text(json.dumps(runtime_payload, indent=2), encoding="utf-8")
    version = subprocess.run([cellranger, "--version"], check=False, capture_output=True, text=True)
    version_text = (version.stdout or version.stderr).strip().splitlines()
    (results_dir / "software_versions.json").write_text(
        json.dumps({"software": [{"name": "cellranger", "version": version_text[0] if version_text else ""}]}, indent=2),
        encoding="utf-8",
    )
    if args.prepare_only:
        print(f"[info] prepared {len(commands)} Cell Ranger multi configuration(s)")
        return 0
    for command in commands:
        print("+", " ".join(shlex.quote(part) for part in command), flush=True)
        subprocess.run(command, cwd=results_dir, check=True)
    subprocess.run(
        [
            sys.executable,
            str(workspace / "collect_qc.py"),
            "--results-dir",
            str(results_dir),
        ],
        check=True,
    )
    print(f"[info] completed {len(commands)} Cell Ranger multi run(s) in {results_dir}")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "render":
        return render_workspace(args)
    return execute_workspace(args)


if __name__ == "__main__":
    raise SystemExit(main())
