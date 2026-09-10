#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
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
    assert run.selected_obs_keys(adata, []) == ["sample_id", "leiden", "custom"]
    assert run.selected_obs_keys(adata, ["*"]) == ["sample_id", "leiden", "custom"]


def test_obs_preparation_skips_high_cardinality_columns() -> None:
    run = load_run_module()
    adata = ad.AnnData(
        X=sparse.csr_matrix(np.ones((3, 2))),
        obs=pd.DataFrame(
            {
                "ok": ["a", "b", "b"],
                "too_many": ["c1", "c2", "c3"],
            },
            index=["cell1", "cell2", "cell3"],
        ),
        var=pd.DataFrame(index=["gene_a", "gene_b"]),
    )
    original_limit = run.LOUPE_MAX_CATEGORIES
    run.LOUPE_MAX_CATEGORIES = 2
    try:
        warnings: list[str] = []
        keys = run.prepare_obs_for_loupe(adata, ["ok", "too_many"], warnings)
    finally:
        run.LOUPE_MAX_CATEGORIES = original_limit
    assert keys == ["ok"]
    assert str(adata.obs["ok"].dtype) == "category"
    assert "too_many" in warnings[0]


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


def test_default_output_is_next_to_input() -> None:
    run = load_run_module()
    input_h5ad = Path("/tmp/project/results/adata.prep.h5ad")
    output = run.resolve_output({"output_cloupe": ""}, input_h5ad)
    metadata = run.resolve_metadata_path({"metadata_json": ""}, output)
    assert output == Path("/tmp/project/results/adata.prep.cloupe")
    assert metadata == Path("/tmp/project/results/adata.prep_export.json")


def test_input_option_alias() -> None:
    run = load_run_module()
    args = run.parse_args(["--input", "/tmp/project/results/adata.prep.h5ad"])
    params = run.load_params(args)
    assert params["input"] == "/tmp/project/results/adata.prep.h5ad"
    assert params["input_h5ad"] == "/tmp/project/results/adata.prep.h5ad"


def test_missing_output_file_fails() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "missing.cloupe"
        try:
            run.require_output_file(missing)
        except SystemExit as exc:
            assert "did not create the expected file" in str(exc)
        else:
            raise AssertionError("missing cloupe output should fail")


def test_failed_system_exit_writes_metadata() -> None:
    run = load_run_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_h5ad = tmp_path / "input.h5ad"
        output_cloupe = tmp_path / "output.cloupe"
        metadata_json = tmp_path / "metadata.json"
        adata = ad.AnnData(
            X=sparse.csr_matrix(np.ones((2, 2))),
            obs=pd.DataFrame(index=["cell1", "cell2"]),
            var=pd.DataFrame(index=["gene_a", "gene_b"]),
        )
        adata.obsm["X_umap"] = np.ones((2, 2))
        adata.write_h5ad(input_h5ad)

        args = run.parse_args(
            [
                "--input",
                str(input_h5ad),
                "--output",
                str(output_cloupe),
                "--metadata",
                str(metadata_json),
                "--counts-layer",
                "missing_counts",
            ]
        )
        original_parse_args = run.parse_args
        run.parse_args = lambda: args
        try:
            try:
                run.main()
            except SystemExit as exc:
                assert "missing_counts" in str(exc)
            else:
                raise AssertionError("missing counts layer should fail")
        finally:
            run.parse_args = original_parse_args

        payload = json.loads(metadata_json.read_text(encoding="utf-8"))
        assert payload["status"]["state"] == "failed"
        assert "missing_counts" in payload["status"]["errors"][0]


def test_synthetic_barcode_mode_preserves_original_ids() -> None:
    run = load_run_module()
    adata = ad.AnnData(
        X=sparse.csr_matrix(np.ones((2, 2))),
        obs=pd.DataFrame(index=["sampleA:cell1", "sampleB:cell2"]),
        var=pd.DataFrame(index=["gene_a", "gene_b"]),
    )
    original_loader = run.load_synthetic_barcodes
    run.load_synthetic_barcodes = lambda n, source: ["AAACCTGAGAAACCAT", "AAACCTGAGAAACCGC"][:n]
    try:
        warnings: list[str] = []
        obs_keys = run.prepare_barcodes_for_loupe(
            adata,
            {
                "barcode_mode": "synthetic_10x",
                "barcode_whitelist": "",
                "original_barcode_key": "original_cell_id",
                "synthetic_barcode_key": "loupe_synthetic_barcode",
            },
            [],
            warnings,
        )
    finally:
        run.load_synthetic_barcodes = original_loader
    assert adata.obs_names.tolist() == ["AAACCTGAGAAACCAT", "AAACCTGAGAAACCGC"]
    assert adata.obs["original_cell_id"].tolist() == ["sampleA:cell1", "sampleB:cell2"]
    assert adata.obs["pipseq_sample"].tolist() == ["sampleA", "sampleB"]
    assert {"original_cell_id", "loupe_synthetic_barcode", "pipseq_sample"}.issubset(obs_keys)
    assert warnings


def test_software_versions_contract() -> None:
    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "software_versions_spec.yaml").read_text(encoding="utf-8")
    assert "software_versions:" in template_text
    assert "path: results/software_versions.json" in template_text
    assert 'python3 "${pack_root}/functions/software_versions.py"' in run_sh_text
    assert "WRITE_SOFTWARE_VERSIONS" in run_sh_text
    assert 'linkar collect "${script_dir}"' in run_sh_text
    assert 'LINKAR_COLLECT' in run_sh_text
    assert 'LINKAR_CLEAN' in run_sh_text
    assert "counts_layer" in spec_text
    assert "output_cloupe" in template_text
    assert "barcode_mode" in template_text


def test_help_does_not_require_template_dependencies() -> None:
    result = subprocess.run(
        [sys.executable, "-S", str(TEMPLATE_DIR / "run.py"), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--counts-layer" in result.stdout


def main() -> int:
    test_obs_key_selection()
    test_obs_preparation_skips_high_cardinality_columns()
    test_validate_counts_layer()
    test_resolve_input()
    test_default_output_is_next_to_input()
    test_input_option_alias()
    test_missing_output_file_fails()
    test_failed_system_exit_writes_metadata()
    test_synthetic_barcode_mode_preserves_original_ids()
    test_software_versions_contract()
    test_help_does_not_require_template_dependencies()
    print("cloupe tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
