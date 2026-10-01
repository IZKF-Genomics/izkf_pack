from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path
from typing import Any


MOLECULE_KEYS = (
    "per_sample_molecule_info",
    "molecule_info",
    "molecule_info_files",
)
SAMPLE_OUTS_KEYS = ("per_sample_outs_dirs", "sample_outs_dirs")
VDJ_KEYS = ("vdj_contig_info", "vdj_contig_info_files")
PLACEHOLDER = "__EDIT_ME__"


def _cache_root() -> Path:
    linkar_home = str(os.getenv("LINKAR_HOME") or "").strip()
    if linkar_home:
        return Path(linkar_home).expanduser().resolve() / "generated_samplesheets"
    return Path.home().resolve() / ".linkar" / "generated_samplesheets"


def _as_paths(value: Any) -> list[Path]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return sorted({Path(str(item)).expanduser().resolve() for item in values if str(item).strip()})


def _project_entries(ctx: Any) -> list[dict[str, Any]]:
    project = getattr(ctx, "project", None)
    data = getattr(project, "data", {}) if project is not None else {}
    entries = (data or {}).get("templates") or []
    return [entry for entry in entries if isinstance(entry, dict)]


def _latest_candidate(ctx: Any) -> tuple[str, dict[str, Any]]:
    supported = {"cellranger_multi", "cellranger_count", "cellranger_vdj"}
    for entry in reversed(_project_entries(ctx)):
        template_id = str(entry.get("id") or "")
        if template_id not in supported:
            continue
        outputs = entry.get("outputs") or {}
        if not isinstance(outputs, dict):
            continue
        if any(outputs.get(key) for key in (*MOLECULE_KEYS, *SAMPLE_OUTS_KEYS, *VDJ_KEYS)):
            return template_id, outputs
    raise RuntimeError(
        "cellranger aggr inputs could not be generated: no collected cellranger_multi, "
        "cellranger_count, or cellranger_vdj outputs were found in the current project. "
        "Run and collect an upstream Cell Ranger template first, or provide --aggregation-csv explicitly."
    )


def _require_existing(paths: list[Path], label: str) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        preview = "\n  - ".join(missing[:8])
        suffix = "\n  - ..." if len(missing) > 8 else ""
        raise RuntimeError(
            f"cellranger aggr binding found missing {label} path(s):\n  - {preview}{suffix}\n"
            "Re-run 'linkar collect' for the upstream template or provide an explicit aggregation CSV."
        )


def _sample_id_for_molecule(path: Path) -> str:
    if path.name == "sample_molecule_info.h5":
        if path.parent.name == "count":
            return path.parent.parent.name
        return path.parent.name
    if path.name == "molecule_info.h5" and path.parent.name == "outs":
        return path.parent.parent.name
    return path.stem.replace(".molecule_info", "")


def _sample_outs_for_molecule(path: Path) -> Path:
    if path.name == "sample_molecule_info.h5" and path.parent.name == "count":
        return path.parent.parent
    return path.parent


def _sample_id_for_vdj(path: Path) -> str:
    if path.parent.name in {"vdj_b", "vdj_t", "vdj_t_gd"}:
        return path.parent.parent.name
    if path.parent.name == "outs":
        return path.parent.parent.name
    return path.parent.name


def _library_set(sample_outs: Path) -> tuple[str, ...]:
    libraries: set[str] = set()
    if (
        (sample_outs / "sample_molecule_info.h5").exists()
        or (sample_outs / "count").is_dir()
        or (sample_outs / "sample_filtered_feature_bc_matrix.h5").exists()
    ):
        libraries.add("count")
    for name in ("vdj_b", "vdj_t", "vdj_t_gd"):
        if (sample_outs / name).is_dir():
            libraries.add(name)
    return tuple(sorted(libraries))


def _write_csv(fieldnames: list[str], rows: list[dict[str, str]], signature: str) -> str:
    digest = hashlib.sha1(signature.encode()).hexdigest()[:12]
    out_dir = _cache_root() / "cellranger_aggr" / digest
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / "aggregation.csv"
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(destination.resolve())


def _from_sample_outs(paths: list[Path]) -> str:
    _require_existing(paths, "sample_outs")
    library_sets = {_library_set(path) for path in paths}
    if len(library_sets) != 1:
        details = "; ".join(f"{path.name}={','.join(_library_set(path)) or 'unknown'}" for path in paths)
        raise RuntimeError(
            "cellranger aggr full-multi inputs have inconsistent library combinations: " + details
        )
    rows = [
        {
            "sample_id": path.name,
            "sample_outs": str(path),
            "donor": PLACEHOLDER,
            "origin": PLACEHOLDER,
        }
        for path in paths
    ]
    return _write_csv(
        ["sample_id", "sample_outs", "donor", "origin"],
        rows,
        "sample_outs\n" + "\n".join(str(path) for path in paths),
    )


def resolve(ctx: Any) -> str:
    template_id, outputs = _latest_candidate(ctx)

    explicit_sample_outs: list[Path] = []
    for key in SAMPLE_OUTS_KEYS:
        explicit_sample_outs.extend(_as_paths(outputs.get(key)))
    if explicit_sample_outs:
        return _from_sample_outs(sorted(set(explicit_sample_outs)))

    molecules: list[Path] = []
    for key in MOLECULE_KEYS:
        molecules.extend(_as_paths(outputs.get(key)))
    molecules = sorted(set(molecules))
    if molecules:
        _require_existing(molecules, "molecule_info")
        sample_outs = sorted(
            {_sample_outs_for_molecule(path) for path in molecules if path.name == "sample_molecule_info.h5"}
        )
        if sample_outs and any(any((path / name).is_dir() for name in ("vdj_b", "vdj_t")) for path in sample_outs):
            return _from_sample_outs(sample_outs)
        rows = [
            {"sample_id": _sample_id_for_molecule(path), "molecule_h5": str(path)}
            for path in molecules
        ]
        return _write_csv(
            ["sample_id", "molecule_h5"],
            rows,
            f"{template_id}\nmolecule_h5\n" + "\n".join(str(path) for path in molecules),
        )

    vdj_paths: list[Path] = []
    for key in VDJ_KEYS:
        vdj_paths.extend(_as_paths(outputs.get(key)))
    vdj_paths = sorted(set(vdj_paths))
    if vdj_paths:
        _require_existing(vdj_paths, "vdj_contig_info")
        rows = [
            {
                "sample_id": _sample_id_for_vdj(path),
                "vdj_contig_info": str(path),
                "donor": PLACEHOLDER,
                "origin": PLACEHOLDER,
            }
            for path in vdj_paths
        ]
        return _write_csv(
            ["sample_id", "vdj_contig_info", "donor", "origin"],
            rows,
            f"{template_id}\nvdj_contig_info\n" + "\n".join(str(path) for path in vdj_paths),
        )

    raise RuntimeError(
        f"the latest {template_id} entry does not expose a supported Cell Ranger aggr input"
    )
