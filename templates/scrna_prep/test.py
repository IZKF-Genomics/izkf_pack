#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


TEMPLATE_DIR = Path(__file__).resolve().parent
FUNCTIONS_DIR = TEMPLATE_DIR.parent.parent / "functions"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_function(name: str):
    return load_module(FUNCTIONS_DIR / f"{name}.py", f"test_{name}").resolve


def assert_fails(command: list[str], expected_message: str, *, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert expected_message in combined


def assert_system_exit(callback, expected_message: str) -> None:
    try:
        callback()
    except SystemExit as exc:
        assert expected_message in str(exc)
        return
    raise AssertionError("Expected SystemExit")


class FakeProject:
    def __init__(self, templates: list[dict]) -> None:
        self.data = {"templates": templates}


class FakeTemplate:
    root = TEMPLATE_DIR


class FakeContext:
    def __init__(self, templates: list[dict]) -> None:
        self.project = FakeProject(templates)
        self.template = FakeTemplate()
        self.resolved_params = {}

    def latest_output(self, key: str, template_id: str | None = None):
        for entry in reversed(self.project.data["templates"]):
            if template_id is not None and entry.get("id") != template_id:
                continue
            outputs = entry.get("outputs") or {}
            if key in outputs:
                return outputs[key]
        return None


def main() -> int:
    run_module = load_module(TEMPLATE_DIR / "run.py", "test_scrna_prep_run")

    with tempfile.TemporaryDirectory(prefix="linkar-scverse-scrna-prep-test-") as tmp:
        tmp_path = Path(tmp)
        project_dir = tmp_path / "260417_scRNA_Project"
        results_dir = tmp_path / "results"
        project_dir.mkdir()
        results_dir.mkdir()
        (project_dir / "project.yaml").write_text(yaml.safe_dump({}, sort_keys=False), encoding="utf-8")

        input_h5ad = tmp_path / "input.h5ad"
        input_h5ad.write_text("placeholder", encoding="utf-8")
        input_h5 = tmp_path / "filtered_feature_bc_matrix.h5"
        input_h5.write_text("placeholder", encoding="utf-8")

        tenx_mtx_dir = tmp_path / "filtered_feature_bc_matrix"
        tenx_mtx_dir.mkdir()
        (tenx_mtx_dir / "matrix.mtx").write_text("%%MatrixMarket matrix coordinate integer general\n", encoding="utf-8")
        (tenx_mtx_dir / "features.tsv").write_text("gene1\tGene1\tGene Expression\n", encoding="utf-8")
        (tenx_mtx_dir / "barcodes.tsv").write_text("cell-1\n", encoding="utf-8")

        parsebio_dir = tmp_path / "parsebio_run"
        parsebio_dir.mkdir()
        (parsebio_dir / "count_matrix.mtx").write_text("%%MatrixMarket matrix coordinate integer general\n", encoding="utf-8")
        (parsebio_dir / "all_genes.csv").write_text("gene_id,gene_name\nENSG1,Gene1\n", encoding="utf-8")
        (parsebio_dir / "cell_metadata.csv").write_text("bc_wells,sample_id\ncell-1,s1\n", encoding="utf-8")

        scalebio_dir = tmp_path / "scalebio_counts"
        scalebio_dir.mkdir()
        (scalebio_dir / "matrix.mtx").write_text("%%MatrixMarket matrix coordinate integer general\n", encoding="utf-8")
        (scalebio_dir / "features.tsv").write_text("gene1\tGene1\tGene Expression\n", encoding="utf-8")
        (scalebio_dir / "barcodes.tsv").write_text("cell-1\n", encoding="utf-8")

        per_sample_outs_dir = tmp_path / "per_sample_outs"
        sample_count_dir = per_sample_outs_dir / "sampleA" / "count"
        sample_count_dir.mkdir(parents=True)
        (sample_count_dir / "sample_filtered_feature_bc_matrix.h5").write_text("placeholder", encoding="utf-8")

        unknown_dir = tmp_path / "unknown_input"
        unknown_dir.mkdir()

        metadata_csv = tmp_path / "sample_metadata.csv"
        metadata_csv.write_text("sample_id,batch,condition,sample_label\nsampleA,b1,treated,Sample A\n", encoding="utf-8")
        missing_metadata = tmp_path / "missing_metadata.csv"

        minimal_params = {
            "input_h5ad": str(input_h5ad),
            "input_matrix": "",
            "input_source_template": "",
            "ambient_correction_applied": "false",
            "ambient_correction_method": "none",
            "input_format": "h5ad",
            "var_names": "gene_symbols",
            "sample_metadata": "",
            "organism": "human",
            "batch_key": "batch",
            "condition_key": "condition",
            "sample_id_key": "sample_id",
            "doublet_method": "scrublet",
            "filter_predicted_doublets": "true",
            "qc_mode": "fixed",
            "qc_nmads": "3.0",
            "min_genes": "200",
            "min_cells": "3",
            "min_counts": "500",
            "max_pct_counts_mt": "20.0",
            "max_pct_counts_ribo": "",
            "max_pct_counts_hb": "",
            "n_top_hvgs": "3000",
            "n_pcs": "30",
            "n_neighbors": "15",
            "leiden_resolution": "",
            "resolution_grid": "0.2,0.4,0.6,0.8,1.0,1.2",
        }

        assert run_module.detect_input_format(input_h5ad) == "h5ad"
        assert run_module.detect_input_format(input_h5) == "10x_h5"
        assert run_module.detect_input_format(tenx_mtx_dir) == "10x_mtx"
        assert run_module.detect_input_format(parsebio_dir) == "parsebio"
        assert run_module.detect_input_format(scalebio_dir) == "scalebio"
        assert run_module.detect_input_format(per_sample_outs_dir) == "cellranger_per_sample_outs"
        assert run_module.detect_input_format(unknown_dir) == ""

        run_module.validate_params(dict(minimal_params))

        invalid_input_params = dict(minimal_params)
        invalid_input_params["input_h5ad"] = ""
        assert_system_exit(
            lambda: run_module.validate_params(invalid_input_params),
            "Set INPUT_H5AD or INPUT_MATRIX before running scrna_prep.",
        )

        duplicate_input_params = dict(minimal_params)
        duplicate_input_params["input_matrix"] = str(input_h5)
        assert_system_exit(
            lambda: run_module.validate_params(duplicate_input_params),
            "Set only one of INPUT_H5AD or INPUT_MATRIX before running scrna_prep.",
        )

        missing_input_path_params = dict(minimal_params)
        missing_input_path_params["input_h5ad"] = str(tmp_path / "does_not_exist.h5ad")
        assert_system_exit(
            lambda: run_module.validate_params(missing_input_path_params),
            "INPUT_H5AD does not exist:",
        )

        wrong_h5ad_suffix_params = dict(minimal_params)
        wrong_h5ad_suffix_params["input_h5ad"] = str(input_h5)
        assert_system_exit(
            lambda: run_module.validate_params(wrong_h5ad_suffix_params),
            "INPUT_H5AD must point to a .h5ad file.",
        )

        wrong_h5ad_format_params = dict(minimal_params)
        wrong_h5ad_format_params["input_format"] = "10x_h5"
        assert_system_exit(
            lambda: run_module.validate_params(wrong_h5ad_format_params),
            "Use INPUT_FORMAT=auto or h5ad when INPUT_H5AD is set.",
        )

        matrix_h5ad_params = dict(minimal_params)
        matrix_h5ad_params["input_h5ad"] = ""
        matrix_h5ad_params["input_matrix"] = str(input_h5ad)
        matrix_h5ad_params["input_format"] = "auto"
        assert_system_exit(
            lambda: run_module.validate_params(matrix_h5ad_params),
            "Use INPUT_H5AD for AnnData .h5ad input.",
        )

        auto_detect_fail_params = dict(minimal_params)
        auto_detect_fail_params["input_h5ad"] = ""
        auto_detect_fail_params["input_matrix"] = str(unknown_dir)
        auto_detect_fail_params["input_format"] = "auto"
        assert_system_exit(
            lambda: run_module.validate_params(auto_detect_fail_params),
            "Could not determine INPUT_FORMAT for INPUT_MATRIX automatically.",
        )

        explicit_dir_required_params = dict(minimal_params)
        explicit_dir_required_params["input_h5ad"] = ""
        explicit_dir_required_params["input_matrix"] = str(input_h5)
        explicit_dir_required_params["input_format"] = "10x_mtx"
        assert_system_exit(
            lambda: run_module.validate_params(explicit_dir_required_params),
            "INPUT_MATRIX points to a file, but INPUT_FORMAT=10x_mtx expects a directory.",
        )

        missing_organism_params = dict(minimal_params)
        missing_organism_params["organism"] = ""
        assert_system_exit(
            lambda: run_module.validate_params(missing_organism_params),
            "Set ORGANISM to a supported alias for QC gene annotation before running scrna_prep.",
        )

        unsupported_organism_params = dict(minimal_params)
        unsupported_organism_params["organism"] = "zebrafish"
        assert_system_exit(
            lambda: run_module.validate_params(unsupported_organism_params),
            "Received: zebrafish.",
        )

        missing_metadata_params = dict(minimal_params)
        missing_metadata_params["sample_metadata"] = str(missing_metadata)
        assert_system_exit(
            lambda: run_module.validate_params(missing_metadata_params),
            "SAMPLE_METADATA does not exist.",
        )

        directory_metadata_params = dict(minimal_params)
        directory_metadata_params["sample_metadata"] = str(TEMPLATE_DIR)
        assert_system_exit(
            lambda: run_module.validate_params(directory_metadata_params),
            "Set SAMPLE_METADATA to a CSV file path, not a directory.",
        )

        invalid_var_names_params = dict(minimal_params)
        invalid_var_names_params["var_names"] = "symbols"
        assert_system_exit(
            lambda: run_module.validate_params(invalid_var_names_params),
            "Set VAR_NAMES to one of:",
        )

        invalid_doublet_method_params = dict(minimal_params)
        invalid_doublet_method_params["doublet_method"] = "solo"
        assert_system_exit(
            lambda: run_module.validate_params(invalid_doublet_method_params),
            "Set DOUBLET_METHOD to one of:",
        )

        invalid_doublet_combo_params = dict(minimal_params)
        invalid_doublet_combo_params["doublet_method"] = "none"
        invalid_doublet_combo_params["filter_predicted_doublets"] = "true"
        assert_system_exit(
            lambda: run_module.validate_params(invalid_doublet_combo_params),
            "FILTER_PREDICTED_DOUBLETS requires DOUBLET_METHOD=scrublet",
        )

        invalid_qc_mode_params = dict(minimal_params)
        invalid_qc_mode_params["qc_mode"] = "adaptive"
        assert_system_exit(
            lambda: run_module.validate_params(invalid_qc_mode_params),
            "Set QC_MODE to one of:",
        )

        invalid_pct_params = dict(minimal_params)
        invalid_pct_params["max_pct_counts_mt"] = "101"
        assert_system_exit(
            lambda: run_module.validate_params(invalid_pct_params),
            "Set MAX_PCT_COUNTS_MT to a numeric value <= 100.0.",
        )

        invalid_resolution_grid_params = dict(minimal_params)
        invalid_resolution_grid_params["resolution_grid"] = "0.2,-0.4"
        assert_system_exit(
            lambda: run_module.validate_params(invalid_resolution_grid_params),
            "Set RESOLUTION_GRID to a numeric value >= 1e-06.",
        )

        alias_matrix_params = dict(minimal_params)
        alias_matrix_params["input_h5ad"] = ""
        alias_matrix_params["input_matrix"] = str(tenx_mtx_dir)
        alias_matrix_params["input_format"] = "10x_mtx"
        alias_matrix_params["organism"] = "mus_musculus"
        alias_matrix_params["sample_metadata"] = str(metadata_csv)
        run_module.validate_params(alias_matrix_params)

        (TEMPLATE_DIR / "config").mkdir(exist_ok=True)
        run_module.write_project_config(
            TEMPLATE_DIR / "config" / "project.toml",
            minimal_params,
            project_name=project_dir.name,
            sample_metadata="assets/samples.csv",
        )
        original_project_dir = run_module.PROJECT_DIR
        original_results_dir = run_module.RESULTS_DIR
        run_module.PROJECT_DIR = project_dir
        run_module.RESULTS_DIR = results_dir
        try:
            run_module.write_run_info(
                results_dir / "run_info.yaml",
                minimal_params,
                project_name=project_dir.name,
                sample_metadata="assets/samples.csv",
            )
        finally:
            run_module.PROJECT_DIR = original_project_dir
            run_module.RESULTS_DIR = original_results_dir

        config_text = (TEMPLATE_DIR / "config" / "project.toml").read_text(encoding="utf-8")
        run_info = yaml.safe_load((results_dir / "run_info.yaml").read_text(encoding="utf-8"))

        assert 'name = "260417_scRNA_Project"' in config_text
        assert f'input_h5ad = "{input_h5ad}"' in config_text
        assert 'input_format = "h5ad"' in config_text
        assert 'doublet_method = "scrublet"' in config_text
        assert "filter_predicted_doublets = true" in config_text
        assert 'sample_metadata = "assets/samples.csv"' in config_text
        assert "authors =" not in config_text

        assert run_info["params"]["project_name"] == "260417_scRNA_Project"
        assert run_info["params"]["organism"] == "human"
        assert run_info["params"]["filter_predicted_doublets"] is True
        assert run_info["params"]["sample_metadata"] == "assets/samples.csv"
        assert "authors" not in run_info["params"]

        base_env = {**os.environ, "LINKAR_PACK_ROOT": str(TEMPLATE_DIR.parent.parent)}
        assert_fails(
            [sys.executable, str(TEMPLATE_DIR / "run.py")],
            "Set INPUT_H5AD or INPUT_MATRIX before running scrna_prep.",
            env=base_env,
        )
        assert_fails(
            [sys.executable, str(TEMPLATE_DIR / "run.py")],
            "Set ORGANISM to a supported alias for QC gene annotation before running scrna_prep.",
            env={**base_env, "INPUT_H5AD": str(input_h5ad)},
        )
        assert_fails(
            [sys.executable, str(TEMPLATE_DIR / "run.py")],
            "Use INPUT_H5AD for AnnData .h5ad input.",
            env={
                **base_env,
                "INPUT_MATRIX": str(input_h5ad),
                "INPUT_FORMAT": "auto",
                "ORGANISM": "human",
            },
        )
        assert_fails(
            [sys.executable, str(TEMPLATE_DIR / "run.py")],
            "FILTER_PREDICTED_DOUBLETS requires DOUBLET_METHOD=scrublet",
            env={
                **base_env,
                "INPUT_H5AD": str(input_h5ad),
                "ORGANISM": "human",
                "DOUBLET_METHOD": "none",
                "FILTER_PREDICTED_DOUBLETS": "true",
            },
        )

        temp_workspace = tmp_path / "render_workspace"
        temp_results_dir = temp_workspace / "results"
        temp_reports_dir = temp_workspace / "reports"
        temp_config_dir = temp_workspace / "config"
        temp_assets_dir = temp_workspace / "assets"
        temp_project_dir = tmp_path / "260418_scRNA_Render"
        temp_workspace.mkdir()
        temp_assets_dir.mkdir()
        temp_project_dir.mkdir()
        commands: list[list[str]] = []
        original_globals = {
            "PROJECT_DIR": run_module.PROJECT_DIR,
            "RESULTS_DIR": run_module.RESULTS_DIR,
            "REPORTS_DIR": run_module.REPORTS_DIR,
            "CONFIG_DIR": run_module.CONFIG_DIR,
            "NOTEBOOK_PATH": run_module.NOTEBOOK_PATH,
            "SOFTWARE_VERSIONS_SPEC": run_module.SOFTWARE_VERSIONS_SPEC,
            "PROJECT_CONFIG_PATH": run_module.PROJECT_CONFIG_PATH,
            "RUN_INFO_PATH": run_module.RUN_INFO_PATH,
            "run_command": run_module.run_command,
        }
        tracked_env = {
            key: os.environ.get(key)
            for key in [
                "INPUT_H5AD",
                "INPUT_MATRIX",
                "INPUT_SOURCE_TEMPLATE",
                "AMBIENT_CORRECTION_APPLIED",
                "AMBIENT_CORRECTION_METHOD",
                "INPUT_FORMAT",
                "VAR_NAMES",
                "SAMPLE_METADATA",
                "ORGANISM",
            ]
        }
        try:
            run_module.PROJECT_DIR = temp_project_dir
            run_module.RESULTS_DIR = temp_results_dir
            run_module.REPORTS_DIR = temp_reports_dir
            run_module.CONFIG_DIR = temp_config_dir
            run_module.NOTEBOOK_PATH = temp_workspace / "scrna_prep.qmd"
            run_module.SOFTWARE_VERSIONS_SPEC = temp_assets_dir / "software_versions_spec.yaml"
            run_module.PROJECT_CONFIG_PATH = temp_config_dir / "project.toml"
            run_module.RUN_INFO_PATH = temp_results_dir / "run_info.yaml"
            run_module.run_command = lambda cmd: commands.append(cmd)
            os.environ["INPUT_H5AD"] = ""
            os.environ["INPUT_MATRIX"] = str(tenx_mtx_dir)
            os.environ["INPUT_SOURCE_TEMPLATE"] = "manual"
            os.environ["AMBIENT_CORRECTION_APPLIED"] = "false"
            os.environ["AMBIENT_CORRECTION_METHOD"] = "none"
            os.environ["INPUT_FORMAT"] = "10x_mtx"
            os.environ["VAR_NAMES"] = "gene_symbols"
            os.environ.pop("SAMPLE_METADATA", None)
            os.environ["ORGANISM"] = "mouse"

            assert run_module.main(["--prepare-only"]) == 0

            orchestration_config = (temp_config_dir / "project.toml").read_text(encoding="utf-8")
            orchestration_run_info = yaml.safe_load((temp_results_dir / "run_info.yaml").read_text(encoding="utf-8"))
            assert 'sample_metadata = "assets/samples.csv"' in orchestration_config
            assert f'input_matrix = "{tenx_mtx_dir}"' in orchestration_config
            assert orchestration_run_info["params"]["sample_metadata"] == "assets/samples.csv"
            assert temp_results_dir.exists()
            assert temp_reports_dir.exists()
            assert temp_config_dir.exists()
            assert commands == []
        finally:
            run_module.PROJECT_DIR = original_globals["PROJECT_DIR"]
            run_module.RESULTS_DIR = original_globals["RESULTS_DIR"]
            run_module.REPORTS_DIR = original_globals["REPORTS_DIR"]
            run_module.CONFIG_DIR = original_globals["CONFIG_DIR"]
            run_module.NOTEBOOK_PATH = original_globals["NOTEBOOK_PATH"]
            run_module.SOFTWARE_VERSIONS_SPEC = original_globals["SOFTWARE_VERSIONS_SPEC"]
            run_module.PROJECT_CONFIG_PATH = original_globals["PROJECT_CONFIG_PATH"]
            run_module.RUN_INFO_PATH = original_globals["RUN_INFO_PATH"]
            run_module.run_command = original_globals["run_command"]
            for key, value in tracked_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    subprocess.run(
        [
            "bash",
            "-lc",
            """pixi run python - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, str(Path("lib").resolve()))
import numpy as np
import anndata as ad
from scrna_prep_io import ensure_preprocessing_counts_matrix, RAW_H5AD_ERROR

counts = ad.AnnData(X=np.array([[1, 0], [3, 4]], dtype=float))
counts = ensure_preprocessing_counts_matrix(counts, input_format="h5ad")
assert "counts" in counts.layers

normalized = ad.AnnData(X=np.array([[0.1, 1.2], [2.3, 3.4]], dtype=float))
try:
    ensure_preprocessing_counts_matrix(normalized, input_format="h5ad")
except RuntimeError as exc:
    assert RAW_H5AD_ERROR in str(exc)
else:
    raise AssertionError("expected raw-count validation failure")

layered = ad.AnnData(X=np.array([[0.1, 0.2], [0.3, 0.4]], dtype=float))
layered.layers["counts"] = np.array([[5, 0], [7, 9]], dtype=float)
layered = ensure_preprocessing_counts_matrix(layered, input_format="h5ad")
assert np.array_equal(np.asarray(layered.X), np.asarray(layered.layers["counts"]))

sparse_counts = ad.AnnData(X=__import__("scipy").sparse.csr_matrix(np.random.poisson(1.0, size=(30, 12))))
import scanpy as sc
import pandas as pd
from scrna_prep_io import looks_like_gene_ids, normalize_text_series, resolve_qc_feature_names
sc.pp.normalize_total(sparse_counts, target_sum=1e4)
sc.pp.log1p(sparse_counts)
sc.pp.highly_variable_genes(sparse_counts, n_top_genes=5, flavor="seurat")
sc.tl.pca(sparse_counts, n_comps=4, svd_solver="arpack", mask_var="highly_variable")
assert __import__("scipy").sparse.issparse(sparse_counts.X)
assert sparse_counts.obsm["X_pca"].shape == (30, 4)

var = pd.DataFrame(
    {"gene_symbols": ["MT-CO1", "RPS18", "HBZ"]},
    index=["ENSG00000198888", "ENSG00000140988", "ENSG00000206172"],
)
resolved = resolve_qc_feature_names(var, var.index)
assert resolved.tolist() == ["MT-CO1", "RPS18", "HBZ"]
assert looks_like_gene_ids(pd.Index(var.index))
normalized = normalize_text_series(pd.Series([None, np.nan, "", " nan ", "treated"]), fallback="unknown")
assert normalized.tolist() == ["unknown", "unknown", "unknown", "unknown", "treated"]
PY""",
        ],
        cwd=TEMPLATE_DIR,
        check=True,
    )

    upstream_templates = [
        {
            "id": "nfcore_scrnaseq",
            "params": {"genome": "GRCz11", "aligner": "star"},
            "outputs": {
                "selected_matrix_h5ad": "/tmp/results/star/mtx_conversions/combined_cellbender_filter_matrix.h5ad",
            },
        }
    ]
    ctx = FakeContext(upstream_templates)
    assert load_function("get_scrna_prep_input_h5ad")(ctx) == "/tmp/results/star/mtx_conversions/combined_cellbender_filter_matrix.h5ad"
    assert load_function("get_scrna_prep_input_source_template")(ctx) == "nfcore_scrnaseq"
    assert load_function("get_scrna_prep_ambient_correction_applied")(ctx) is True
    assert load_function("get_scrna_prep_ambient_correction_method")(ctx) == "cellbender"
    assert load_function("get_scrna_prep_organism")(ctx) == "drerio"

    template_text = (TEMPLATE_DIR / "linkar_template.yaml").read_text(encoding="utf-8")
    run_sh_text = (TEMPLATE_DIR / "run.sh").read_text(encoding="utf-8")
    run_py_text = (TEMPLATE_DIR / "run.py").read_text(encoding="utf-8")
    qmd_text = (TEMPLATE_DIR / "scrna_prep.qmd").read_text(encoding="utf-8")
    readme_text = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    spec_text = (TEMPLATE_DIR / "assets" / "software_versions_spec.yaml").read_text(encoding="utf-8")

    assert "id: scrna_prep" in template_text
    assert "exactly one of `input_h5ad` or `input_matrix`" in template_text.lower()
    assert "requires `doublet_method=scrublet`" in template_text
    assert 'cd "${script_dir}"' in run_sh_text
    assert 'python3 "run.py" --prepare-only' in run_sh_text
    assert "pixi install" in run_sh_text
    assert 'pixi run quarto render "scrna_prep.qmd"' in run_sh_text
    assert "--prepare-only" in run_py_text
    assert "detect_input_format" in run_py_text
    assert "FILTER_PREDICTED_DOUBLETS requires DOUBLET_METHOD=scrublet" in run_py_text
    assert "from scipy import sparse" in qmd_text
    assert "resolve_input_selection" in qmd_text
    assert "sample metadata file was not found" in qmd_text
    assert 'title: "scRNA Preprocessing QC"' in qmd_text
    assert "config/project.toml" in readme_text
    assert "Minimal `.h5ad` handoff" in readme_text
    assert "10x / Cell Ranger HDF5" in readme_text
    assert "10x MTX directory" in readme_text
    assert "ParseBio directory" in readme_text
    assert "ScaleBio or STARsolo-style MTX directory" in readme_text
    assert "Cell Ranger `per_sample_outs` directory" in readme_text
    assert "Automatic handoff from `nfcore_scrnaseq`" in readme_text
    assert "selected_matrix_h5ad" in readme_text
    assert "doublet_method" in spec_text
    assert "scrna_prep_h5ad:\n    path: adata.prep.h5ad" in template_text
    assert 'glob: "*.h5ad"' in template_text
    assert 'mask_var="highly_variable"' in qmd_text
    assert "sc.pp.scale(filtered" not in qmd_text
    assert "resolve_qc_feature_names" in qmd_text
    assert 'astype(str).fillna("unknown")' not in qmd_text
    assert "authors:" not in template_text
    assert "--authors" not in run_sh_text
    assert "author:" not in qmd_text

    pack_text = (TEMPLATE_DIR.parent.parent / "linkar_pack.yaml").read_text(encoding="utf-8")
    pack_data = yaml.safe_load(pack_text)
    params = pack_data["templates"]["scrna_prep"]["params"]
    assert params["input_h5ad"]["function"] == "get_scrna_prep_input_h5ad"
    assert params["organism"]["function"] == "get_scrna_prep_organism"

    print("scrna_prep template test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
