#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
import anndata as ad


ROOT = Path(__file__).resolve().parent
TIER3_CONFIG = ROOT / "tier3_formal_annotation" / "config" / "00_formal_annotation_config.yaml"


def build_test_adata(path: Path) -> None:
    X = np.array(
        [
            [5, 4, 0, 0, 1, 0],
            [6, 3, 0, 0, 1, 0],
            [5, 5, 0, 0, 0, 1],
            [4, 4, 0, 0, 0, 1],
            [0, 0, 6, 5, 0, 1],
            [0, 0, 5, 6, 1, 0],
            [0, 1, 5, 5, 0, 0],
            [0, 0, 4, 5, 1, 0],
            [0, 0, 1, 0, 6, 5],
            [1, 0, 0, 0, 5, 6],
            [0, 0, 1, 0, 5, 5],
            [0, 1, 0, 0, 4, 5],
        ],
        dtype=float,
    )
    obs = pd.DataFrame(
        {
            "leiden": ["0"] * 4 + ["1"] * 4 + ["2"] * 4,
            "sample_id": ["s1"] * 6 + ["s2"] * 6,
            "batch": ["b1"] * 12,
            "condition": ["ctrl"] * 12,
            "sample_display": ["Sample 1"] * 6 + ["Sample 2"] * 6,
            "train_label": ["T_cells"] * 4 + ["B_cells"] * 4 + ["Myeloid"] * 4,
        },
        index=[f"cell_{i}" for i in range(12)],
    )
    var = pd.DataFrame(index=["CD3D", "CD3E", "MS4A1", "CD79A", "LYZ", "NKG7"])
    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.layers["counts"] = X.copy()
    adata.obsm["X_umap"] = np.random.default_rng(0).normal(size=(12, 2))
    adata.write_h5ad(path)


def run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=True)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="scrna-annotate-rebuild-test-") as tmp:
        tmpdir = Path(tmp)
        input_h5ad = tmpdir / "input.h5ad"
        workflow_yaml = tmpdir / "workflow.yaml"
        tier3_backup = tmpdir / "tier3_config_backup.yaml"

        build_test_adata(input_h5ad)

        workflow_yaml.write_text(
            yaml.safe_dump(
                {
                    "global": {
                        "input_h5ad": str(input_h5ad),
                        "cluster_key": "leiden",
                        "batch_key": "batch",
                        "condition_key": "condition",
                        "sample_id_key": "sample_id",
                        "sample_label_key": "sample_display",
                        "unknown_label": "Unknown",
                    },
                    "workflow": {
                        "default_tier": "tier1",
                        "auto_recommend_next": True,
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        shutil.copyfile(TIER3_CONFIG, tier3_backup)
        TIER3_CONFIG.write_text(
            yaml.safe_dump(
                {
                    "formal_annotation": {
                        "enabled": True,
                        "method": "celltypist",
                        "majority_vote_min_fraction": 0.6,
                        "confidence_threshold": 0.5,
                        "predicted_label_key": "formal_label_celltypist",
                        "final_label_key": "final_label",
                        "rank_top_markers": 5,
                        "marker_file": "",
                    },
                    "celltypist": {
                        "model": "dummy_model.pkl",
                        "mode": "best_match",
                        "p_thres": 0.5,
                        "use_gpu": False,
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        env = {
            **subprocess.os.environ,
            "SCRNA_ANNOTATE_WORKFLOW_CONFIG": str(workflow_yaml),
            "LINKAR_TEST_CELLTYPIST_MOCK": "1",
        }

        try:
            run(["bash", "run.sh", "--from", "tier1", "--to", "tier3"], env=env)
            assert (ROOT / "reports" / "00_overview.html").exists()
            assert (ROOT / "tier1_quick_preview" / "reports" / "01_quick_preview.html").exists()
            assert (ROOT / "tier2_refinement" / "reports" / "02_refinement.html").exists()
            assert (ROOT / "tier3_formal_annotation" / "reports" / "03_formal_annotation.html").exists()
            assert (ROOT / "tier3_formal_annotation" / "results" / "adata.annotated.h5ad").exists()
            formal_predictions = pd.read_csv(ROOT / "tier3_formal_annotation" / "results" / "tables" / "formal_annotation_predictions.csv")
            formal_summary = pd.read_csv(ROOT / "tier3_formal_annotation" / "results" / "tables" / "formal_annotation_summary.csv")
            assert not formal_predictions.empty
            assert not formal_summary.empty
        finally:
            shutil.copyfile(tier3_backup, TIER3_CONFIG)
            for path in [
                ROOT / "reports",
                ROOT / "tier1_quick_preview" / "results",
                ROOT / "tier1_quick_preview" / "reports",
                ROOT / "tier2_refinement" / "results",
                ROOT / "tier2_refinement" / "reports",
                ROOT / "tier3_formal_annotation" / "results",
                ROOT / "tier3_formal_annotation" / "reports",
            ]:
                if path.exists():
                    shutil.rmtree(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
