# tests/test_excel_mcp_context.py
import asyncio
import pandas as pd
import pytest
from src.excel_mcp_context import ExcelMCPConnector, build_tool_name

def make_connector(df=None, slug="sales"):
    if df is None:
        df = pd.DataFrame({"month": ["Jan", "Feb"], "revenue": [100, 200]})
    return ExcelMCPConnector(slug=slug, df=df, display_name="sales.xlsx")

def test_build_tool_name_basic():
    assert build_tool_name("My Sales 2024.xlsx") == "query_my_sales_2024"

def test_build_tool_name_strips_special_chars():
    assert build_tool_name("  Q1 Report! (Final).xlsx") == "query_q1_report_final"

def test_build_tool_name_max_length():
    result = build_tool_name("a" * 80)
    assert len(result) <= 64

def test_list_tools_returns_one_tool():
    c = make_connector()
    tools = c.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "query_sales"
    assert "sql" in tools[0]["input_schema"]["properties"]

def test_call_tool_returns_json():
    c = make_connector()
    result = asyncio.run(c.call_tool("query_sales", {"sql": "SELECT * FROM data"}))
    assert "month" in result

def test_call_tool_missing_sql_raises():
    c = make_connector()
    with pytest.raises(ValueError, match="sql argument required"):
        asyncio.run(c.call_tool("query_sales", {}))

def test_call_tool_readonly_check():
    c = make_connector()
    for bad_sql in ["DROP TABLE data", "DELETE FROM data", "INSERT INTO data VALUES (1)"]:
        with pytest.raises(ValueError):
            asyncio.run(c.call_tool("query_sales", {"sql": bad_sql}))

def test_call_tool_wrong_tool_name_raises():
    c = make_connector()
    with pytest.raises(ValueError, match="Unknown tool"):
        asyncio.run(c.call_tool("query_other", {"sql": "SELECT 1"}))

def test_empty_dataframe_raises_at_init():
    with pytest.raises(ValueError, match="no data"):
        ExcelMCPConnector(slug="empty", df=pd.DataFrame(columns=["a", "b"]), display_name="empty.xlsx")

def test_no_columns_dataframe_raises():
    with pytest.raises(ValueError, match="no columns"):
        ExcelMCPConnector(slug="nocols", df=pd.DataFrame(index=[0, 1]), display_name="x.xlsx")

def test_tool_description_contains_table_name():
    c = make_connector()
    assert "data" in c.list_tools()[0]["description"]
