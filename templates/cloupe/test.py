#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


TEMPLATE_DIR = Path(__file__).resolve().parent


def load_run_module():
    sys.path.insert(0, str(TEMPLATE_DIR))
    spec = importlib.util.spec_from_file_location("cloupe_run", TEMPLATE_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_obs_key_selection() -> None:
    run = load_run_module()
    adata = ad.AnnData(
        X=sparse.csr_matrix(np.array([[1, 0], [0, 2]], dtype=np.float32)),
        obs=pd.DataFrame(
            {
                "sample_id": ["s1", "s2"],
                "leiden": ["0", "1"],
                "custom": ["a", "b"],
            },
            index=["cell1", "cell2"],
        ),
        var=pd.DataFrame(index=["gene_a", "gene_b"]),
    )
    keys = run.selected_obs_keys(adata, ["custom", "missing"])
    assert keys == ["sample_id", "leiden", "custom"]


def test_validate_counts_layer() -> None:
    run = load_run_module()
    adata = ad.AnnData(
        X=sparse.csr_matrix(np.array([[1, 0], [0, 2]], dtype=np.float32)),
        var=pd.DataFrame(index=["gene_a", "gene_b"]),
    )
    adata.layers["counts"] = sparse.csr_matrix(np.array([[5, 0], [0, 7]], dtype=np.float32))
    warnings: list[str] = []
    assert run.validate_counts_layer(adata, "counts", warnings) == "counts"
    assert not warnings


def test_resolve_input() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.h5ad"
        ad.AnnData(X=sparse.csr_matrix(np.ones((2, 2)))).write_h5ad(path)
        resolved = run.resolve_input({"input": str(path), "input_h5ad": ""})
        assert resolved == path


def test_software_versions_contract() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "software_versions:" in template_text
    assert "path: results/software_versions.json" in template_text
    assert 'python3 "${pack_root}/functions/software_versions.py"' in run_sh_text
    assert '--spec "${script_dir}/software_versions_spec.yaml"' in run_sh_text
    assert "counts_layer" in spec_text


def main() -> int:
    test_obs_key_selection()
    test_validate_counts_layer()
    test_resolve_input()
    test_software_versions_contract()
    print("cloupe tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
