from __future__ import annotations

from io import BytesIO
import asyncio

import duckdb
import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def isolated_server(monkeypatch, tmp_path):
    import backend.server as server
    from backend.storage import Storage
    from src.mcp_pool import get_pool

    storage = Storage(tmp_path / "app.sqlite")
    monkeypatch.setattr(server, "DB", storage)
    monkeypatch.setattr(server, "API_KEY", "")
    if hasattr(server, "USER_AUTH_REQUIRED"):
        monkeypatch.setattr(server, "USER_AUTH_REQUIRED", False)
    get_pool().connectors.clear()
    yield server, storage, get_pool()
    get_pool().connectors.clear()


def _write_workbook(path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def test_selected_excel_sheets_become_tables_in_one_duckdb(tmp_path):
    from src.data_sources import prepare_excel_workbook_duckdb_sources

    workbook = tmp_path / "operations.xlsx"
    _write_workbook(
        workbook,
        {
            "Orders": pd.DataFrame({"Order ID": [1, 2], "Revenue": [10.5, 20.0]}),
            "Inventory": pd.DataFrame({"SKU": ["A", "B"], "Stock": [7, 8]}),
            "Ignored": pd.DataFrame({"Value": [99]}),
        },
    )

    sources = prepare_excel_workbook_duckdb_sources(workbook, ["Orders", "Inventory"], tmp_path / "cache", None)

    assert [source.display_name for source in sources] == ["operations.xlsx - Orders", "operations.xlsx - Inventory"]
    assert len({source.db_path for source in sources}) == 1
    assert [source.table_name for source in sources] == ["orders", "inventory"]
    con = duckdb.connect(sources[0].db_path, read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        assert tables == {"orders", "inventory"}
        assert con.execute('SELECT SUM(revenue) FROM "orders"').fetchone()[0] == pytest.approx(30.5)
    finally:
        con.close()


def test_excel_workbook_table_names_are_safe_and_unique(tmp_path):
    from src.data_sources import prepare_excel_workbook_duckdb_sources

    workbook = tmp_path / "unsafe names.xlsx"
    _write_workbook(
        workbook,
        {
            "2026 Sales!": pd.DataFrame({"Value": [1]}),
            "2026 Sales.": pd.DataFrame({"Value": [2]}),
        },
    )

    sources = prepare_excel_workbook_duckdb_sources(workbook, ["2026 Sales!", "2026 Sales."], tmp_path / "cache", None)

    assert [source.table_name for source in sources] == ["t_2026_sales", "t_2026_sales_2"]


def test_excel_workbook_requires_at_least_one_sheet(tmp_path):
    from src.data_sources import prepare_excel_workbook_duckdb_sources

    workbook = tmp_path / "operations.xlsx"
    _write_workbook(workbook, {"Orders": pd.DataFrame({"Value": [1]})})

    with pytest.raises(ValueError, match="Select at least one sheet"):
        prepare_excel_workbook_duckdb_sources(workbook, [], tmp_path / "cache", None)


def test_excel_workbook_rejects_unknown_sheet(tmp_path):
    from src.data_sources import prepare_excel_workbook_duckdb_sources

    workbook = tmp_path / "operations.xlsx"
    _write_workbook(workbook, {"Orders": pd.DataFrame({"Value": [1]})})

    with pytest.raises(ValueError, match="not found"):
        prepare_excel_workbook_duckdb_sources(workbook, ["Missing"], tmp_path / "cache", None)


def test_workbook_mcp_connector_lists_and_queries_selected_tables(tmp_path):
    from src.data_sources import prepare_excel_workbook_duckdb_sources
    from src.excel_mcp_context import WorkbookMCPConnector

    workbook = tmp_path / "operations.xlsx"
    _write_workbook(
        workbook,
        {
            "Orders": pd.DataFrame({"Order ID": [1, 2], "Revenue": [10, 20]}),
            "Inventory": pd.DataFrame({"SKU": ["A"], "Stock": [4]}),
        },
    )
    sources = prepare_excel_workbook_duckdb_sources(workbook, ["Orders", "Inventory"], tmp_path / "cache", None)
    connector = WorkbookMCPConnector(
        slug="operations",
        db_path=sources[0].db_path,
        table_names=[source.table_name for source in sources],
        display_name="operations.xlsx",
    )

    tools = connector.list_tools()
    assert [tool["name"] for tool in tools] == ["list_operations_tables", "query_operations"]
    table_payload = asyncio.run(connector.call_tool("list_operations_tables", {}))
    assert "orders" in table_payload
    result_payload = asyncio.run(connector.call_tool("query_operations", {"sql": 'SELECT SUM(revenue) AS total FROM "orders"'}))
    assert '"total":30' in result_payload


def test_pending_excel_upload_resolves_multiple_selected_sheets(isolated_server, monkeypatch):
    _server, _storage, _pool = isolated_server
    captured = {}

    def fake_deploy(*, script_name, backend_rpc_url, public_token):
        captured["backend_rpc_url"] = backend_rpc_url
        captured["public_token"] = public_token
        return "https://unipro-workbook-mcp.workers.dev/mcp"

    monkeypatch.setattr(_server, "deploy_cloudflare_workbook_worker", fake_deploy)
    client = TestClient(_server.app)
    payload = BytesIO()
    with pd.ExcelWriter(payload, engine="openpyxl") as writer:
        pd.DataFrame({"Order ID": [1], "Revenue": [25]}).to_excel(writer, sheet_name="Orders", index=False)
        pd.DataFrame({"SKU": ["A"], "Stock": [4]}).to_excel(writer, sheet_name="Inventory", index=False)
    payload.seek(0)

    upload = client.post(
        "/sources/upload",
        files={"file": ("operations.xlsx", payload.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 200
    pending = upload.json()["pending"]
    assert pending["kind"] == "sheet_pick"
    assert pending["multi_select"] is True

    resolved = client.post(
        "/sources/resolve_pending",
        json={"upload_id": pending["upload_id"], "value": ["Orders", "Inventory"], "public_base_url": "https://unipro.share.zrok.io"},
    )

    assert resolved.status_code == 200
    body = resolved.json()
    assert [source["name"] for source in body["sources"]] == [
        "operations.xlsx - Orders",
        "operations.xlsx - Inventory",
    ]
    assert {source["kind"] for source in body["sources"]} == {"xlsx"}
    assert body["mcp_connector"]["status"] == "connected"
    assert body["mcp_connector"]["cloudflare"]["worker_url"] == "https://unipro-workbook-mcp.workers.dev/mcp"
    assert captured["backend_rpc_url"].startswith("https://unipro.share.zrok.io/mcp/workbooks/")
    assert captured["public_token"]
    assert [tool["name"] for tool in body["mcp_connector"]["tools"]] == [
        "list_operations_tables",
        "query_operations",
    ]
