import pytest
import pandas as pd
from backend.server import _df_to_payload

def test_df_to_payload_handles_nat():
    # Arrange: Create a DataFrame with a NaT value
    df = pd.DataFrame({
        "timestamp": [pd.Timestamp("2024-01-01"), pd.NaT],
        "value": [10, 20]
    })
    
    # Act
    payload = _df_to_payload(df)
    
    # Assert
    # The first row should have the correct isoformat
    assert payload["rows"][0][0] == "2024-01-01T00:00:00"
    # The second row should have None (null in JSON), NOT "NaT"
    assert payload["rows"][1][0] is None

def test_assert_public_url_is_async():
    import asyncio
    from backend.server import _assert_public_url
    
    # This will fail (TypeError) if _assert_public_url is synchronous,
    # driving us to make it async.
    asyncio.run(_assert_public_url("http://example.com"))

def test_workspace_sql_sync_path_traversal(monkeypatch):
    from backend.server import _run_workspace_sql_sync

    connected_path = None

    class MockDuckDB:
        def connect(self, path, read_only=False):
            nonlocal connected_path
            connected_path = path
            class MockCon:
                def execute(self, sql):
                    return self
                def fetchdf(self):
                    import pandas as pd
                    return pd.DataFrame()
                def close(self):
                    pass
            return MockCon()

    monkeypatch.setattr("duckdb.connect", MockDuckDB().connect)

    chat_id = "../../../tmp/hacked"
    _run_workspace_sql_sync(chat_id, "SELECT 1")

    assert "tmp" not in str(connected_path)
    assert str(connected_path).endswith("hacked.duckdb")

def test_parse_tool_result_handles_large_csv():
    from src.mcp_pool import parse_tool_result_to_dataframe
    large_csv = "a,b,c\n" + "1,2,3\n" * 1000
    df = parse_tool_result_to_dataframe(large_csv)
    assert df is not None
    assert len(df) == 1000


@pytest.fixture()
def isolated_server(monkeypatch, tmp_path):
    import backend.server as server
    from backend.storage import Storage
    from src.mcp_pool import get_pool

    storage = Storage(tmp_path / "app.sqlite")
    monkeypatch.setattr(server, "DB", storage)
    get_pool().connectors.clear()
    yield server, storage, get_pool()
    get_pool().connectors.clear()


def test_project_mcp_endpoints_bind_and_unbind(isolated_server):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    project = storage.create_project("Scoped")
    storage.upsert_mcp_connector(
        connector_id="mysql",
        name="MySQL",
        scope="project",
        transport="stdio",
        url=None,
        command="mcp-server-mysql",
        args=["mysql://user:pass@example.test/db"],
        tools=[{"name": "query", "description": "Run SQL"}],
        status="connected",
        last_error=None,
        description="MySQL exposes 1 tool: query.",
        generated_description=None,
        description_status="metadata",
    )

    client = TestClient(server.app)
    assert client.get(f"/projects/{project['id']}/mcp").json() == []

    bind = client.post(f"/projects/{project['id']}/mcp/mysql")
    assert bind.status_code == 200
    assert bind.json()["ok"] is True

    linked = client.get(f"/projects/{project['id']}/mcp").json()
    assert linked[0]["id"] == "mysql"
    assert linked[0]["args"] == ["[redacted]"]

    unbind = client.delete(f"/projects/{project['id']}/mcp/mysql")
    assert unbind.status_code == 200
    assert client.get(f"/projects/{project['id']}/mcp").json() == []


def test_sources_mcp_synthetic_source_uses_project_scope(isolated_server):
    server, storage, pool = isolated_server
    from fastapi.testclient import TestClient
    from src.mcp_pool import ConnectorState

    project = storage.create_project("Scoped")
    for connector_id, scope, tool_name in [
        ("global-db", "global", "global_query"),
        ("project-db", "project", "project_query"),
        ("other-db", "project", "other_query"),
    ]:
        state = ConnectorState(id=connector_id, name=connector_id, status="connected")
        state.tools = [{"name": tool_name, "description": f"{tool_name} description", "input_schema": {}}]
        pool.connectors[connector_id] = state
        storage.upsert_mcp_connector(
            connector_id=connector_id,
            name=connector_id,
            scope=scope,
            transport="stdio",
            url=None,
            command="mcp-server",
            args=[],
            tools=state.tools,
            status="connected",
            last_error=None,
            description=f"{connector_id} exposes 1 tool: {tool_name}.",
            generated_description=None,
            description_status="metadata",
        )
    storage.bind_mcp_to_project(project["id"], "project-db")

    sources = TestClient(server.app).get(f"/sources?project_id={project['id']}").json()

    mcp_source = sources[0]
    assert mcp_source["id"] == "mcp"
    assert mcp_source["rows"] == 2
    assert "global-db" in mcp_source["name"]
    assert "project-db" in mcp_source["name"]
    assert "other-db" not in mcp_source["name"]


def test_allowed_mcp_ids_for_project_chat_include_global_and_project(isolated_server):
    server, storage, _pool = isolated_server
    project = storage.create_project("Scoped")
    chat = storage.create_chat("Chat")
    storage.update_chat_project(chat["id"], project["id"])
    for connector_id, scope in [("global-db", "global"), ("project-db", "project"), ("hidden-db", "project")]:
        storage.upsert_mcp_connector(
            connector_id=connector_id,
            name=connector_id,
            scope=scope,
            transport="stdio",
            url=None,
            command="mcp-server",
            args=[],
            tools=[{"name": f"{connector_id}_query"}],
            status="connected",
            last_error=None,
            description=f"{connector_id} exposes tools.",
            generated_description=None,
            description_status="metadata",
        )
    storage.bind_mcp_to_project(project["id"], "project-db")

    assert server._allowed_mcp_connector_ids_for_chat(chat["id"]) == {"global-db", "project-db"}
    assert server._allowed_mcp_connector_ids_for_chat(None) == {"global-db"}
