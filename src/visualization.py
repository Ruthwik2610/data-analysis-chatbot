from __future__ import annotations

import re
from typing import Any

import pandas as pd


_EXPLICIT_VIZ_RE = re.compile(r"\b(pie|donut|bar|line|table|chart|graph)\b", re.I)


def explicit_visualization(question: str) -> str | None:
    match = _EXPLICIT_VIZ_RE.search(question)
    if not match:
        return None
    word = match.group(1).lower()
    if word == "donut":
        return "pie"
    if word in {"chart", "graph"}:
        return "bar"
    return word


def choose_visualization(question: str, intent: dict[str, Any], df: pd.DataFrame) -> str:
    explicit = explicit_visualization(question)
    if explicit:
        return explicit
    requested = str(intent.get("requested_visualization") or "auto").lower()
    if requested in {"table", "bar", "line", "pie", "card"}:
        return requested
    if df.empty:
        return "table"
    if intent.get("intent_type") == "lookup":
        return "table"

    cols = list(df.columns)
    n_rows = len(df)
    q = question.lower()

    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    dim_cols = [c for c in cols if c not in numeric_cols]

    # No numeric column means there's nothing to chart — render as table.
    if not numeric_cols:
        return "table"

    if "period" in cols:
        return "line"
    if n_rows == 1 and len(cols) <= 3:
        return "card"
    if n_rows <= 3 and re.search(r"\btop\s+3\b|\btop three\b", q):
        return "table"

    # 2+ dimensions + 1 numeric → stacked bar (frontend will pivot)
    if len(dim_cols) >= 2 and len(numeric_cols) >= 1:
        return "table" if n_rows > 200 else "bar"

    # 1 dimension + 1 numeric
    if len(dim_cols) == 1 and len(numeric_cols) >= 1:
        non_negative = bool(df[numeric_cols[0]].dropna().ge(0).all()) if not df[numeric_cols[0]].dropna().empty else True
        if (
            2 <= n_rows <= 8
            and non_negative
            and any(t in q for t in ["share", "percentage", "percent", "distribution", "breakdown", "split", "composition"])
        ):
            return "pie"
        if n_rows > 25:
            return "table"
        if n_rows >= 2:
            return "bar"

    return "table"


def deterministic_summary(question: str, df: pd.DataFrame, row_count: int) -> str:
    if df.empty:
        return "I couldn't find matching rows in the CSV for that question."
    if len(df) == 1 and len(df.columns) <= 3:
        values = ", ".join(f"**{col.replace('_', ' ').title()}**: {df.iloc[0][col]}" for col in df.columns)
        return f"{values}. Based on {row_count:,} result row."
    return f"I found {row_count:,} result row{'s' if row_count != 1 else ''}. The table below contains the verified result from DuckDB."
