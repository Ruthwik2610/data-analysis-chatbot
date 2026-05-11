from __future__ import annotations

import asyncio
from dataclasses import replace

import duckdb
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


def _create_workbook_connector(tmp_path, pool, storage, connector_id: str = "mcp_workbook"):
    db_path = tmp_path / "workbook.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE orders AS SELECT 1 AS order_id, 10 AS revenue UNION ALL SELECT 2, 20")
        con.execute("CREATE TABLE customers AS SELECT 1 AS order_id, 'Retail' AS segment UNION ALL SELECT 2, 'Enterprise'")
    finally:
        con.close()
    asyncio.run(
        pool.connect_excel_workbook(
            str(db_path),
            ["orders", "customers"],
            "operations.xlsx",
            connector_id=connector_id,
        )
    )
    storage.upsert_mcp_connector(
        connector_id=connector_id,
        name="operations.xlsx workbook",
        scope="global",
        transport="local_workbook",
        url=None,
        command=None,
        args=[],
        tools=pool.connectors[connector_id].tools,
        status="connected",
        last_error=None,
        description="Workbook MCP",
        generated_description=None,
        description_status="metadata",
    )
    storage.upsert_workbook_mcp_metadata(
        connector_id=connector_id,
        db_path=str(db_path),
        table_names=["orders", "customers"],
        display_name="operations.xlsx",
    )
    return db_path


def test_workbook_mcp_rpc_requires_token_and_calls_tools(isolated_server, tmp_path):
    server, storage, pool = isolated_server
    _create_workbook_connector(tmp_path, pool, storage)
    deployment = storage.upsert_workbook_mcp_deployment(
        connector_id="mcp_workbook",
        worker_name="unipro-workbook-mcp",
        worker_url="https://unipro-workbook-mcp.example.workers.dev/mcp",
        public_token="secret-token",
    )
    assert "public_token" not in deployment

    client = TestClient(server.app)
    unauthorized = client.post(
        "/mcp/workbooks/mcp_workbook/rpc",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert unauthorized.status_code == 401

    listed = client.post(
        "/mcp/workbooks/mcp_workbook/rpc",
        headers={"x-workbook-mcp-token": "secret-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert listed.status_code == 200
    assert [tool["name"] for tool in listed.json()["result"]["tools"]] == [
        "list_operations_tables",
        "query_operations",
    ]

    called = client.post(
        "/mcp/workbooks/mcp_workbook/rpc",
        headers={"x-workbook-mcp-token": "secret-token"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "query_operations", "arguments": {"sql": "SELECT SUM(revenue) AS total FROM orders"}},
        },
    )
    assert called.status_code == 200
    assert '"total":30' in called.json()["result"]["content"][0]["text"]


def test_cloudflare_deploy_endpoint_publishes_workbook_rpc_url(isolated_server, tmp_path, monkeypatch):
    server, storage, pool = isolated_server
    _create_workbook_connector(tmp_path, pool, storage)
    monkeypatch.setattr(server, "CONFIG", replace(server.CONFIG, admin_password="admin"))
    admin_token = __import__("hashlib").sha256(b"admin").hexdigest()
    captured = {}

    def fake_deploy(*, script_name, backend_rpc_url, public_token):
        captured["script_name"] = script_name
        captured["backend_rpc_url"] = backend_rpc_url
        captured["public_token"] = public_token
        return "https://unipro-workbook-mcp.workers.dev/mcp"

    monkeypatch.setattr(server, "deploy_cloudflare_workbook_worker", fake_deploy)

    response = TestClient(server.app).post(
        "/mcp/connectors/mcp_workbook/cloudflare",
        headers={"x-admin-token": admin_token},
        json={"public_base_url": "https://unipro.share.zrok.io"},
    )

    assert response.status_code == 200
    assert response.json()["worker_url"] == "https://unipro-workbook-mcp.workers.dev/mcp"
    assert captured["backend_rpc_url"] == "https://unipro.share.zrok.io/mcp/workbooks/mcp_workbook/rpc"
    assert captured["public_token"]
    assert "public_token" not in response.text


def test_workbook_views_can_be_created_merged_modified_and_deleted(isolated_server, tmp_path):
    server, storage, pool = isolated_server
    _create_workbook_connector(tmp_path, pool, storage)
    client = TestClient(server.app)

    created = client.post(
        "/mcp/connectors/mcp_workbook/views",
        json={"name": "revenue_by_order", "sql": "SELECT order_id, revenue FROM orders"},
    )
    assert created.status_code == 200
    assert created.json()["name"] == "revenue_by_order"

    merged = client.post(
        "/mcp/connectors/mcp_workbook/views/merge",
        json={
            "name": "revenue_by_segment",
            "left_table": "orders",
            "right_table": "customers",
            "left_key": "order_id",
            "right_key": "order_id",
            "join_type": "inner",
        },
    )
    assert merged.status_code == 200
    assert "JOIN" in merged.json()["sql"]

    modified = client.patch(
        "/mcp/connectors/mcp_workbook/views/revenue_by_order",
        json={"sql": "SELECT order_id, revenue * 2 AS doubled FROM orders"},
    )
    assert modified.status_code == 200
    assert "doubled" in modified.json()["columns"]

    listed = client.get("/mcp/connectors/mcp_workbook/views")
    assert [view["name"] for view in listed.json()] == ["revenue_by_order", "revenue_by_segment"]

    deleted = client.delete("/mcp/connectors/mcp_workbook/views/revenue_by_order")
    assert deleted.status_code == 200
    assert client.get("/mcp/connectors/mcp_workbook/views").json()[0]["name"] == "revenue_by_segment"


def test_query_loop_metrics_are_reviewable_in_admin(isolated_server, monkeypatch):
    server, storage, _pool = isolated_server
    chat = storage.create_chat("Loop-heavy question")
    user_msg = storage.add_message(chat["id"], "user", "Why is revenue changing?", trace_id="trace123")
    storage.add_query_loop_metrics(
        chat_id=chat["id"],
        message_id=user_msg["id"],
        question="Why is revenue changing?",
        route="multi_source_agent",
        round_count=4,
        tool_call_count=7,
        tool_error_count=2,
        thinking_event_count=9,
    )
    monkeypatch_token = "admintoken"
    monkeypatch.setattr(server, "CONFIG", replace(server.CONFIG, admin_password="admin"))
    monkeypatch_hash = __import__("hashlib").sha256(b"admin").hexdigest()
    assert monkeypatch_hash != monkeypatch_token

    response = TestClient(server.app).get(
        "/admin/query-loops",
        headers={"x-admin-token": monkeypatch_hash},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["high_loop_queries"] == 1
    assert response.json()["queries"][0]["tool_call_count"] == 7
