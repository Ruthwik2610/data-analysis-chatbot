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


class WorkbookMCPConnector:
    """Read-only MCP tools backed by a DuckDB workbook database."""

    def __init__(self, slug: str, db_path: str, table_names: list[str], display_name: str) -> None:
        if not table_names:
            raise ValueError("Workbook connector requires at least one table")
        self.slug = re.sub(r"[^0-9a-zA-Z]+", "_", slug).strip("_").lower() or "workbook"
        self.db_path = db_path
        self.table_names = table_names
        self.display_name = display_name
        self.list_tool_name = f"list_{self.slug}_tables"[:64]
        self.query_tool_name = f"query_{self.slug}"[:64]

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": self.list_tool_name,
                "description": f"List selected Excel workbook tables for '{self.display_name}'.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": self.query_tool_name,
                "description": (
                    f"Run read-only DuckDB SQL against selected Excel sheets from '{self.display_name}'. "
                    f"Tables: {', '.join(self.table_names)}"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "Read-only SQL over the listed workbook tables"}
                    },
                    "required": ["sql"],
                },
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name == self.list_tool_name:
            return json.dumps({"tables": self.table_names})
        if tool_name != self.query_tool_name:
            raise ValueError(f"Unknown tool '{tool_name}' for this connector")
        sql = arguments.get("sql", "").strip()
        if not sql:
            raise ValueError("sql argument required")
        validate_readonly_sql(sql)
        import duckdb
        con = duckdb.connect(self.db_path, read_only=True)
        try:
            result_df = con.execute(sql).fetchdf()
        finally:
            con.close()
        return result_df.to_json(orient="records", date_format="iso")
