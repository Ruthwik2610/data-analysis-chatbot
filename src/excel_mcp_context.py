"""In-process MCP context backed by a pandas DataFrame (Excel source)."""
from __future__ import annotations
import json
import re
from typing import Any
import pandas as pd
from src.query_engine import validate_readonly_sql


def build_tool_name(display_name: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", display_name)
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", stem).strip("_").lower()
    return f"query_{slug}"[:64]


class ExcelMCPConnector:
    """Wraps a DataFrame as a single virtual MCP tool."""

    def __init__(self, slug: str, df: pd.DataFrame, display_name: str) -> None:
        if len(df.columns) == 0:
            raise ValueError("Sheet has no columns")
        if df.empty:
            raise ValueError("Sheet has no data — refusing to create empty context")
        self.slug = slug
        self.df = df
        self.display_name = display_name
        self.tool_name = slug if slug.startswith("query_") else f"query_{slug}"

    def list_tools(self) -> list[dict[str, Any]]:
        return [{
            "name": self.tool_name,
            "description": (
                f"Query Excel context '{self.display_name}' with SQL. "
                f"Table name is 'data'. Columns: {', '.join(self.df.columns)}"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "Read-only SQL; table is named 'data'"}
                },
                "required": ["sql"],
            },
        }]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name != self.tool_name:
            raise ValueError(f"Unknown tool '{tool_name}' for this connector")
        sql = arguments.get("sql", "").strip()
        if not sql:
            raise ValueError("sql argument required")
        validate_readonly_sql(sql)
        import duckdb
        con = duckdb.connect(":memory:")
        try:
            con.register("data", self.df)
            result_df = con.execute(sql).fetchdf()
        finally:
            con.close()
        return result_df.to_json(orient="records", date_format="iso")
