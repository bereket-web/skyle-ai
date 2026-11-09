from __future__ import annotations

import io
import math

import pandas as pd


class CSVAnalysisError(ValueError):
    pass


def profile_csv(data: bytes, *, max_rows: int = 100_000) -> dict:
    if not data:
        raise CSVAnalysisError("The CSV file is empty.")
    try:
        frame = pd.read_csv(io.BytesIO(data), nrows=max_rows + 1)
    except Exception as exc:
        raise CSVAnalysisError("Could not parse this CSV. Check its delimiter, encoding and header row.") from exc
    if frame.empty or len(frame.columns) == 0:
        raise CSVAnalysisError("The CSV has no data rows or columns.")
    if len(frame) > max_rows:
        raise CSVAnalysisError(f"The file exceeds the {max_rows:,}-row analysis limit.")
    if len(frame.columns) > 100:
        raise CSVAnalysisError("The file exceeds the 100-column analysis limit.")
    columns = []
    for name in frame.columns:
        col = frame[name]
        examples = [None if pd.isna(value) else str(value)[:120] for value in col.dropna().head(3).tolist()]
        entry = {
            "name": str(name),
            "inferred_type": str(col.dtype),
            "missing": int(col.isna().sum()),
            "missing_pct": round(float(col.isna().mean() * 100), 2),
            "unique": int(col.nunique(dropna=True)),
            "examples": examples,
        }
        if pd.api.types.is_numeric_dtype(col):
            numeric = col.dropna().astype(float)
            if len(numeric):
                entry["summary"] = {
                    "mean": _finite(round(float(numeric.mean()), 4)),
                    "std": _finite(round(float(numeric.std(ddof=1) if len(numeric) > 1 else 0.0), 4)),
                    "min": _finite(round(float(numeric.min()), 4)),
                    "median": _finite(round(float(numeric.median()), 4)),
                    "max": _finite(round(float(numeric.max()), 4)),
                }
        columns.append(entry)
    numeric = frame.select_dtypes(include="number")
    correlations = []
    if len(numeric.columns) >= 2:
        corr = numeric.corr(numeric_only=True)
        for i, first in enumerate(corr.columns):
            for second in corr.columns[i + 1 :]:
                value = corr.loc[first, second]
                if pd.notna(value):
                    correlations.append({"left": str(first), "right": str(second), "pearson_r": round(float(value), 4)})
    correlations.sort(key=lambda pair: abs(pair["pearson_r"]), reverse=True)
    return {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "duplicate_rows": int(frame.duplicated().sum()),
        "memory_bytes_estimate": int(frame.memory_usage(deep=True).sum()),
        "column_profile": columns,
        "strongest_numeric_correlations": correlations[:10],
        "notes": [
            "Descriptive statistics are computed locally on this upload; no rows are saved by the service.",
            "Correlations are unadjusted Pearson associations and do not imply causation.",
        ],
    }


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None
