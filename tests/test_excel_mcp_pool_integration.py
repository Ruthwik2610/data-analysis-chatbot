# tests/test_excel_mcp_pool_integration.py
import asyncio
import pandas as pd
from src.mcp_pool import MCPPool

def sample_df():
    return pd.DataFrame({"product": ["A", "B"], "units": [10, 20]})

def test_connect_excel_adds_connected_connector():
    pool = MCPPool()
    cid = asyncio.run(pool.connect_excel(df=sample_df(), display_name="sales.xlsx"))
    assert cid in pool.connectors
    assert pool.connectors[cid].status == "connected"

def test_connect_excel_tools_listed():
    pool = MCPPool()
    cid = asyncio.run(pool.connect_excel(df=sample_df(), display_name="sales.xlsx"))
    tools = pool.connectors[cid].tools
    assert len(tools) == 1
    assert tools[0]["name"].startswith("query_")

def test_connect_excel_call_tool_works():
    pool = MCPPool()
    cid = asyncio.run(pool.connect_excel(df=sample_df(), display_name="sales.xlsx"))
    tool_name = pool.connectors[cid].tools[0]["name"]
    result = asyncio.run(pool.call_tool(cid, tool_name, {"sql": "SELECT * FROM data"}))
    assert "product" in result

def test_connect_excel_dedup_same_key():
    pool = MCPPool()
    df = sample_df()
    cid1 = asyncio.run(pool.connect_excel(df=df, display_name="sales.xlsx", dedup_key="k1"))
    cid2 = asyncio.run(pool.connect_excel(df=df, display_name="sales.xlsx", dedup_key="k1"))
    assert cid1 == cid2
    assert len(pool.connectors) == 1

def test_aggregate_tools_includes_excel():
    pool = MCPPool()
    asyncio.run(pool.connect_excel(df=sample_df(), display_name="report.xlsx"))
    specs, routing = pool.aggregate_tools()
    assert any(s["name"].startswith("query_") for s in specs)
