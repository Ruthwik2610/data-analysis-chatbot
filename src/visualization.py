from __future__ import annotations

from typing import Any

import pandas as pd


def explicit_visualization(question: str) -> str | None:
    q = question.lower()
    for chart in ["pie", "donut", "bar", "line", "table"]:
        if chart in q:
            return "pie" if chart == "donut" else chart
    if "chart" in q or "graph" in q:
        return "bar"
    return None


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
    if "period" in df.columns:
        return "line"
    if len(df) == 1:
        return "card"
    limit = int(intent.get("limit") or len(df))
    q = question.lower()
    if "top" in q and limit <= 3:
        return "table"
    if any(term in q for term in ["share", "percentage", "percent", "distribution", "breakdown"]) and 2 <= len(df) <= 8:
        return "pie"
    if len(df) >= 5:
        return "bar"
    return "table"


def deterministic_summary(question: str, df: pd.DataFrame, row_count: int) -> str:
    if df.empty:
        return "I couldn't find matching rows in the CSV for that question."
    if len(df) == 1 and len(df.columns) <= 3:
        values = ", ".join(f"**{col.replace('_', ' ').title()}**: {df.iloc[0][col]}" for col in df.columns)
        return f"{values}. Based on {row_count:,} result row."
    return f"I found {row_count:,} result row{'s' if row_count != 1 else ''}. The table below contains the verified result from DuckDB."
