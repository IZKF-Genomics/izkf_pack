#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("get_demultiplex_render_outdir.py")
SPEC = importlib.util.spec_from_file_location("get_demultiplex_render_outdir", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> None:
    run_name = "20261116_AV261102_261116_Seq00318_SeqMPN-MSCs"
    with tempfile.TemporaryDirectory(prefix="demultiplex-outdir-test-") as tmp:
        original = os.environ.get("IZKF_DEMULTIPLEX_RENDER_ROOT")
        os.environ["IZKF_DEMULTIPLEX_RENDER_ROOT"] = tmp
        try:
            ctx = SimpleNamespace(
                resolved_params={
                    "bcl_dir": f"/data/raw/aviti/AV261102/{run_name}/",
                    "platform": "aviti",
                    "use_api_samplesheet": False,
                }
            )
            assert MODULE.resolve(ctx) == str((Path(tmp) / run_name).resolve())
        finally:
            if original is None:
                os.environ.pop("IZKF_DEMULTIPLEX_RENDER_ROOT", None)
            else:
                os.environ["IZKF_DEMULTIPLEX_RENDER_ROOT"] = original
    print("get_demultiplex_render_outdir tests passed")


if __name__ == "__main__":
    main()
