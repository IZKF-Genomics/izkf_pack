from __future__ import annotations

from pathlib import Path
import importlib.metadata

import pandas as pd


def load_report_context(root: Path) -> dict:
    import yaml

    path = root / "results" / "report_context.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_table(root: Path, path_str: str) -> pd.DataFrame:
    path = root / path_str
    return pd.read_csv(path)


def package_versions_table(packages: list[str]) -> pd.DataFrame:
    rows = []
    for package in packages:
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = "not installed"
        rows.append({"package": package, "version": version})
    return pd.DataFrame(rows)


def format_table(df: pd.DataFrame, digits: int = 3):
    out = df.copy()

    def _fmt_text(value):
        if pd.isna(value):
            return ""
        return str(value)

    def _fmt_int(value):
        if pd.isna(value):
            return ""
        return f"{int(round(float(value))):,}"

    def _fmt_float(value):
        if pd.isna(value):
            return ""
        return f"{float(value):,.{digits}f}"

    formatters = {}
    for col in out.columns:
        series = out[col]
        lower = str(col).lower()
        if pd.api.types.is_integer_dtype(series):
            formatters[col] = _fmt_int
        elif pd.api.types.is_float_dtype(series):
            if "fraction" in lower or "score" in lower or "confidence" in lower:
                formatters[col] = _fmt_float
            else:
                formatters[col] = _fmt_float
        else:
            formatters[col] = _fmt_text

    return (
        out.style
        .hide(axis="index")
        .format(formatters)
        .set_table_attributes('style="width:100%; min-width:100%; table-layout:auto; margin:0;"')
        .set_properties(**{"white-space": "normal"})
        .set_table_styles(
            [
                {"selector": "th", "props": [("text-align", "left"), ("font-weight", "600")]},
                {"selector": "td", "props": [("padding", "0.25rem 0.5rem")]},
                {"selector": "table", "props": [("font-size", "0.95rem"), ("width", "100%")]},
            ]
        )
    )
