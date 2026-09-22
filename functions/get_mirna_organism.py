from __future__ import annotations

import importlib.util
from pathlib import Path


def _common():
    path = Path(__file__).with_name("_mirna_differential_common.py")
    spec = importlib.util.spec_from_file_location("izkf_pack_mirna_common", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load miRNA helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(ctx) -> str:
    common = _common()
    organism = common.map_genome_to_organism(common.latest_param(ctx, "organism"))
    if not organism:
        organism = common.map_genome_to_organism(common.latest_param(ctx, "genome"))
    if organism:
        return organism
    raise RuntimeError("organism could not be resolved from the latest nfcore_smrnaseq genome")
