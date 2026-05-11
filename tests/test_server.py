import pytest
import pandas as pd
from io import BytesIO
from zipfile import ZipFile
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
    import socket
    from backend.server import _assert_public_url

    async def fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    loop = asyncio.new_event_loop()
    try:
        loop.getaddrinfo = fake_getaddrinfo
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_assert_public_url("http://example.com"))
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def test_assert_public_url_rejects_private_resolution():
    import asyncio
    import socket
    from fastapi import HTTPException
    from backend.server import _assert_public_url

    async def fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    loop = asyncio.new_event_loop()
    try:
        loop.getaddrinfo = fake_getaddrinfo
        asyncio.set_event_loop(loop)
        with pytest.raises(HTTPException):
            loop.run_until_complete(_assert_public_url("http://example.com"))
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def test_assert_public_url_returns_coroutine():
    import asyncio
    from backend.server import _assert_public_url

    # This will fail (TypeError) if _assert_public_url is synchronous,
    # driving us to make it async.
    coroutine = _assert_public_url("http://example.com")
    assert asyncio.iscoroutine(coroutine)
    coroutine.close()

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
    monkeypatch.setattr(server, "API_KEY", "")
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


def test_project_can_be_renamed(isolated_server):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    project = storage.create_project("Old sandbox")

    response = TestClient(server.app).patch(
        f"/projects/{project['id']}",
        json={"title": "Restaurant sandbox"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Restaurant sandbox"
    assert storage.get_project(project["id"])["title"] == "Restaurant sandbox"


def test_chats_endpoint_filters_by_project_id(isolated_server):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    project = storage.create_project("Orders")
    project_chat = storage.create_chat("Orders total")
    unscoped_chat = storage.create_chat("General total")
    storage.update_chat_project(project_chat["id"], project["id"])

    client = TestClient(server.app)

    scoped = client.get(f"/chats?project_id={project['id']}").json()
    unscoped = client.get("/chats?project_id=none").json()

    assert [chat["id"] for chat in scoped] == [project_chat["id"]]
    assert [chat["id"] for chat in unscoped] == [unscoped_chat["id"]]


def test_test_runs_expose_progress_fields(isolated_server):
    _server, storage, _pool = isolated_server

    suite = storage.create_test_suite("Smoke")
    storage.add_test_queries(
        suite["id"],
        [
            {"question": "What is revenue?", "category": "Finance"},
            {"question": "What is order count?", "category": "Finance"},
        ],
    )

    run = storage.create_test_run(suite["id"], {"model": "test-model"})
    runs = storage.list_test_runs(suite["id"])

    assert runs[0]["id"] == run["id"]
    assert runs[0]["status"] == "running"
    assert runs[0]["total_count"] == 2
    assert runs[0]["completed_count"] == 0

    query = storage.list_test_queries(suite["id"])[0]
    storage.add_test_evaluation(run["id"], query["id"], "answer", 12.0)
    updated = storage.list_test_runs(suite["id"])[0]

    assert updated["completed_count"] == 1
    assert updated["stats"]["total"] == 1


def test_admin_auto_suite_uses_selected_user_owned_source(isolated_server, monkeypatch):
    import hashlib
    import json
    from dataclasses import replace
    from fastapi.testclient import TestClient

    server, storage, _pool = isolated_server
    monkeypatch.setattr(server, "CONFIG", replace(server.CONFIG, admin_password="admin"))
    storage.upsert_source(
        source_id="src_user_orders",
        owner_id="user_1",
        name="orders.csv",
        kind="csv",
        rows=2,
        schema_json=json.dumps({"columns": [{"name": "order_date"}, {"name": "revenue"}]}),
        origin={"type": "csv"},
    )

    response = TestClient(server.app).post(
        "/admin/testing/suites/auto",
        headers={"x-admin-token": hashlib.sha256(b"admin").hexdigest()},
        json={"source_ids": ["src_user_orders"]},
    )

    assert response.status_code == 200
    assert response.json()["query_count"] >= 3
    suites = storage.list_test_suites()
    assert suites[0]["metadata"]["source_ids"] == ["src_user_orders"]


def test_test_run_uses_live_query_path_with_suite_sources(isolated_server, monkeypatch):
    import asyncio

    server, storage, _pool = isolated_server
    suite = storage.create_test_suite("Live smoke", metadata={"source_ids": ["src_orders"], "model_mode": "flash"})
    storage.add_test_queries(suite["id"], [{"question": "What is revenue?", "category": "Smoke"}])
    run = storage.create_test_run(suite["id"], {
        "source_ids": ["src_orders"],
        "project_id": None,
        "model_mode": "flash",
        "owner_id": "legacy",
    })
    calls = []

    async def fake_live_query(question, snapshot):
        calls.append({"question": question, "snapshot": snapshot})
        return {
            "answer": "Revenue is 42 from the live query path.",
            "latency_ms": 12.0,
            "trace_id": "trace_live",
            "grade": None,
            "reason": None,
        }

    def raw_router_should_not_run(*_args, **_kwargs):
        raise AssertionError("test runs must not bypass the query endpoint")

    monkeypatch.setattr(server, "_collect_live_test_query", fake_live_query, raising=False)
    monkeypatch.setattr(server.ROUTER, "_generate_text", raw_router_should_not_run)

    asyncio.run(server.run_test_suite_background(run["id"], suite["id"], run["snapshot"]))

    evaluations = storage.list_test_evaluations(run["id"])
    assert calls == [{
        "question": "What is revenue?",
        "snapshot": {
            "source_ids": ["src_orders"],
            "project_id": None,
            "model_mode": "flash",
            "owner_id": "legacy",
        },
    }]
    assert evaluations[0]["answer"] == "Revenue is 42 from the live query path."
    assert evaluations[0]["latency_ms"] == 12.0
    assert evaluations[0]["trace_id"] == "trace_live"


def test_admin_feedback_endpoint_lists_review_items(isolated_server, monkeypatch):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server, "_verify_admin", lambda request: None)
    chat = storage.create_chat("Revenue")
    user_message = storage.add_message(chat["id"], "user", "What is revenue?", trace_id="trace_user")
    assistant_message = storage.add_message(chat["id"], "assistant", "Revenue is 10.", trace_id="trace_answer")

    post = TestClient(server.app).post(
        "/feedback",
        json={
            "chat_id": chat["id"],
            "message_id": assistant_message["id"],
            "rating": -1,
            "comment": "Wrong total",
            "category": "bug",
        },
    )
    assert post.status_code == 200

    response = TestClient(server.app).get("/admin/feedback")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["chat_id"] == chat["id"]
    assert item["message_id"] == assistant_message["id"]
    assert item["comment"] == "Wrong total"
    assert item["category"] == "bug"
    assert item["status"] == "open"
    assert item["answer"] == "Revenue is 10."
    assert item["question"] == "What is revenue?"
    assert item["trace_id"] == "trace_answer"


def test_project_notes_endpoints_create_list_and_delete(isolated_server):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    project = storage.create_project("Notes")

    created = client.post(
        f"/projects/{project['id']}/notes",
        json={
            "title": "Revenue finding",
            "content": "Revenue increased by 12%.",
            "source_message_id": "msg_1",
        },
    )

    assert created.status_code == 200
    note = created.json()
    assert note["title"] == "Revenue finding"

    listed = client.get(f"/projects/{project['id']}/notes")
    assert listed.status_code == 200
    assert listed.json()[0]["content"] == "Revenue increased by 12%."

    deleted = client.delete(f"/projects/{project['id']}/notes/{note['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/projects/{project['id']}/notes").json() == []


def test_model_mode_maps_to_safe_model_ids(monkeypatch):
    import backend.server as server

    monkeypatch.setattr(server, "MODEL_PRESETS", {
        "flash": {"model": "openrouter/deepseek/deepseek-v4-flash", "agent_model": "openrouter/deepseek/deepseek-v4-flash", "provider_order": "DeepSeek"},
        "pro": {"model": "openrouter/deepseek/deepseek-v4-pro", "agent_model": "openrouter/deepseek/deepseek-v4-pro", "provider_order": "DeepSeek"},
    })

    assert server._model_preset_for_mode("flash")["model"] == "openrouter/deepseek/deepseek-v4-flash"
    assert server._model_preset_for_mode("pro")["model"] == "openrouter/deepseek/deepseek-v4-pro"
    assert server._model_preset_for_mode("anything-else")["model"] == "openrouter/deepseek/deepseek-v4-flash"


def test_flash_router_uses_deepseek_flash_provider(monkeypatch):
    import backend.server as server

    captured: dict[str, str] = {}

    class FakeRouter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(server, "_ROUTER_CACHE", {})
    monkeypatch.setattr(server, "LLMRouter", FakeRouter)
    monkeypatch.setattr(server, "MODEL_PRESETS", {
        "flash": {
            "model": "openrouter/deepseek/deepseek-v4-flash",
            "agent_model": "openrouter/deepseek/deepseek-v4-flash",
            "provider_order": "DeepSeek",
        },
        "pro": {
            "model": "openrouter/deepseek/deepseek-v4-pro",
            "agent_model": "openrouter/deepseek/deepseek-v4-pro",
            "provider_order": "DeepSeek",
        },
    })

    router = server._router_for_model_mode("flash")

    assert router is not None
    assert captured["model"] == "openrouter/deepseek/deepseek-v4-flash"
    assert captured["openrouter_provider_order"] == "DeepSeek"


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


def test_source_instruction_endpoints_create_and_update(isolated_server):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    storage.upsert_source(
        source_id="src_pizza",
        name="pizza_sales.csv",
        kind="csv",
        rows=48620,
        schema_json='{"columns":[{"name":"order_id"},{"name":"quantity"}],"row_count":48620}',
        origin={"type": "csv_memory", "path": "/tmp/pizza_sales.csv"},
    )

    client = TestClient(server.app)
    initial = client.get("/sources/src_pizza/instructions")
    assert initial.status_code == 200
    assert initial.json()["instructions"]["entities"]["order"] == "order_id"

    updated = client.patch(
        "/sources/src_pizza/instructions",
        json={
            "instructions": {
                "row_grain": "line_item",
                "entities": {"order": "order_id"},
                "metrics": {"items_sold": {"column": "quantity", "aggregation": "sum"}},
                "notes": "Pizza rows are order line items.",
            }
        },
    )

    assert updated.status_code == 200
    assert updated.json()["instructions"]["notes"] == "Pizza rows are order line items."


def test_project_instruction_endpoints_and_rebuild(isolated_server):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    project = storage.create_project("Pizza sales")
    client = TestClient(server.app)

    patched = client.patch(
        f"/projects/{project['id']}/instructions",
        json={"instructions": {"category": "sales", "notes": "Use restaurant KPI definitions."}},
    )
    assert patched.status_code == 200
    assert patched.json()["instructions"]["category"] == "sales"

    rebuilt = client.post(f"/projects/{project['id']}/profile/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["instructions"]["category"] == "sales"


def test_project_memory_search_is_project_scoped(isolated_server):
    _server, storage, _pool = isolated_server

    p1 = storage.create_project("Pizza")
    p2 = storage.create_project("Finance")
    storage.upsert_project_instructions(p1["id"], {"category": "sales", "notes": "Orders are unique order_id values."})
    storage.upsert_project_instructions(p2["id"], {"category": "finance", "notes": "Invoices are bill numbers."})
    storage.rebuild_project_memory(p1["id"])
    storage.rebuild_project_memory(p2["id"])

    results = storage.search_project_memory(p1["id"], "orders invoices", limit=5)

    assert any("order_id" in item["content"] for item in results)
    assert all("Invoices are bill numbers" not in item["content"] for item in results)


def test_project_vocabulary_learning_is_project_scoped_and_limited(isolated_server):
    server, storage, _pool = isolated_server

    project = storage.create_project("Restaurant ops")
    storage.upsert_project_instructions(project["id"], {"category": "general", "notes": "", "metrics": {}, "entities": {}})
    storage.upsert_source(
        source_id="src_orders",
        name="orders.csv",
        kind="csv",
        rows=10,
        schema_json='{"columns":[{"name":"order_id"},{"name":"gmv"},{"name":"customer_segment"}]}',
        origin={"type": "csv"},
    )
    storage.add_file_to_project(project["id"], None, source_id="src_orders")

    server._learn_project_vocabulary(
        project["id"],
        "legacy",
        "Show gmv by customer segment and promo cohort for restaurant ops",
    )

    instructions = storage.get_project_instructions(project["id"])
    assert instructions["category"] == "sales"
    assert instructions["dynamic_vocabulary"]["gmv"]["count"] == 1
    assert instructions["dynamic_vocabulary"]["gmv"]["columns"] == ["gmv"]
    assert instructions["dynamic_vocabulary"]["segment"]["columns"] == ["customer_segment"]
    assert "show" not in instructions["dynamic_vocabulary"]


def test_user_analytics_surfaces_shared_industry_glossary_candidates(isolated_server, monkeypatch):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server, "_verify_admin", lambda request: None)
    for title in ("Restaurant east", "Restaurant west"):
        project = storage.create_project(title)
        storage.upsert_project_instructions(project["id"], {
            "category": "sales",
            "dynamic_vocabulary": {
                "gmv": {"count": 2, "columns": ["gmv"]},
                "promo": {"count": 1},
            },
        })
    finance = storage.create_project("Finance")
    storage.upsert_project_instructions(finance["id"], {
        "category": "finance",
        "dynamic_vocabulary": {"gmv": {"count": 1}},
    })

    response = TestClient(server.app).get("/admin/user-analytics")

    assert response.status_code == 200
    assert response.json()["industry_vocabulary"] == [
        {"industry": "sales", "term": "gmv", "project_count": 2, "columns": ["gmv"]},
        {"industry": "sales", "term": "promo", "project_count": 2, "columns": []},
    ]


def test_upload_response_includes_clarification_suggestions(isolated_server, monkeypatch, tmp_path):
    server, _storage, _pool = isolated_server
    from fastapi.testclient import TestClient
    from src.data_sources import DataSource

    def fake_prepare_csv_memory_source(path, logger):
        return DataSource(
            source_kind="CSV memory",
            schema={
                "row_count": 48620,
                "columns": [
                    {"name": "order_details_id", "type": "BIGINT"},
                    {"name": "order_id", "type": "BIGINT"},
                    {"name": "quantity", "type": "BIGINT"},
                ],
            },
            display_name=path.name,
            dataframe=pd.DataFrame({"order_details_id": [1, 2], "order_id": [1, 1], "quantity": [1, 2]}),
        )

    monkeypatch.setattr(server, "prepare_csv_memory_source", fake_prepare_csv_memory_source)

    response = TestClient(server.app).post(
        "/sources/upload",
        files={"file": ("pizza_sales.csv", b"order_details_id,order_id,quantity\n1,1,1\n", "text/csv")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["clarifications"][0]["id"] == "row_grain"
    assert "line item" in data["clarifications"][0]["question"].lower()


def test_source_clarification_updates_instructions(isolated_server):
    server, storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    storage.upsert_source(
        source_id="src_pizza",
        name="pizza_sales.csv",
        kind="csv",
        rows=48620,
        schema_json='{"columns":[{"name":"order_id"},{"name":"quantity"}],"row_count":48620}',
        origin=None,
    )

    response = TestClient(server.app).post(
        "/sources/src_pizza/clarifications",
        json={"answers": {"row_grain": "line_item"}},
    )

    assert response.status_code == 200
    assert response.json()["instructions"]["row_grain"] == "line_item"


def test_upload_zip_auto_adds_pdf_sources(isolated_server, monkeypatch):
    server, _storage, _pool = isolated_server
    from fastapi.testclient import TestClient
    from src.data_sources import DataSource

    def fake_prepare_pdf_source(path, logger):
        return DataSource(
            source_kind="PDF table",
            schema={"row_count": 2, "columns": [{"name": "region", "type": "object"}]},
            display_name=path.name,
            dataframe=pd.DataFrame({"region": ["North", "South"]}),
        )

    monkeypatch.setattr(server, "prepare_pdf_source", fake_prepare_pdf_source)
    archive = BytesIO()
    with ZipFile(archive, "w") as zf:
        zf.writestr("reports/april.pdf", b"%PDF-1.4 april")
        zf.writestr("may.pdf", b"%PDF-1.4 may")
        zf.writestr("notes.txt", "ignore me")
    archive.seek(0)

    response = TestClient(server.app).post(
        "/sources/upload",
        files={"file": ("reports.zip", archive.getvalue(), "application/zip")},
    )

    assert response.status_code == 200
    body = response.json()
    assert [source["kind"] for source in body["sources"]] == ["pdf", "pdf"]
    assert {source["name"] for source in body["sources"]} == {"april.pdf", "may.pdf"}
    assert body["skipped"] == []


def test_upload_7z_auto_adds_pdf_sources(isolated_server, monkeypatch, tmp_path):
    server, _storage, _pool = isolated_server
    from fastapi.testclient import TestClient
    from src.data_sources import DataSource

    def fake_extract_7z(path, destination_dir):
        pdf_path = destination_dir / "april.pdf"
        destination_dir.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 april")
        return [pdf_path]

    def fake_prepare_pdf_source(path, logger):
        return DataSource(
            source_kind="PDF table",
            schema={"row_count": 2, "columns": [{"name": "region", "type": "object"}]},
            display_name=path.name,
            dataframe=pd.DataFrame({"region": ["North", "South"]}),
        )

    monkeypatch.setattr(server, "_extract_pdf_members_from_7z", fake_extract_7z)
    monkeypatch.setattr(server, "prepare_pdf_source", fake_prepare_pdf_source)

    response = TestClient(server.app).post(
        "/sources/upload",
        files={"file": ("reports.7z", b"fake 7z bytes", "application/x-7z-compressed")},
    )

    assert response.status_code == 200
    body = response.json()
    assert [source["kind"] for source in body["sources"]] == ["pdf"]
    assert body["sources"][0]["name"] == "april.pdf"


def test_archive_upload_skips_oversized_pdf_members(isolated_server, monkeypatch):
    server, _storage, _pool = isolated_server
    from src.data_sources import DataSource

    monkeypatch.setattr(server, "ARCHIVE_PDF_MAX_BYTES", 10)

    small_pdf = server.UPLOAD_DIR / "small.pdf"
    large_pdf = server.UPLOAD_DIR / "large.pdf"
    small_pdf.write_bytes(b"%PDF-1.4")
    large_pdf.write_bytes(b"%PDF-1.4 oversized")

    prepared = []

    def fake_extract_archive(path, destination_dir):
        return [small_pdf, large_pdf]

    def fake_prepare_pdf_source(path, logger):
        prepared.append(path.name)
        return DataSource(
            source_kind="PDF table",
            schema={"row_count": 1, "columns": [{"name": "region", "type": "object"}]},
            display_name=path.name,
            dataframe=pd.DataFrame({"region": ["North"]}),
        )

    monkeypatch.setattr(server, "_extract_pdf_members_from_archive", fake_extract_archive)
    monkeypatch.setattr(server, "prepare_pdf_source", fake_prepare_pdf_source)

    sources, skipped = server._prepare_archive_pdf_sources(server.UPLOAD_DIR / "reports.7z", server.UPLOAD_DIR / "unpacked")

    assert [source["name"] for source in sources] == ["small.pdf"]
    assert prepared == ["small.pdf"]
    assert skipped == [{"file_name": "large.pdf", "error": "PDF is too large to auto-read from an archive (max 0.0 MB). Upload this PDF directly or export it to CSV/XLSX."}]


def test_archive_upload_does_not_reject_large_pdf_members_when_size_cap_disabled(isolated_server, monkeypatch):
    server, _storage, _pool = isolated_server
    from src.data_sources import DataSource

    monkeypatch.setattr(server, "ARCHIVE_PDF_MAX_BYTES", 0)

    large_pdf = server.UPLOAD_DIR / "large.pdf"
    large_pdf.write_bytes(b"%PDF-1.4 oversized")
    prepared = []

    def fake_extract_archive(path, destination_dir):
        return [large_pdf]

    def fake_prepare_pdf_source(path, logger):
        prepared.append(path.name)
        return DataSource(
            source_kind="PDF table",
            schema={"row_count": 1, "columns": [{"name": "region", "type": "object"}]},
            display_name=path.name,
            dataframe=pd.DataFrame({"region": ["North"]}),
        )

    monkeypatch.setattr(server, "_extract_pdf_members_from_archive", fake_extract_archive)
    monkeypatch.setattr(server, "prepare_pdf_source", fake_prepare_pdf_source)

    sources, skipped = server._prepare_archive_pdf_sources(server.UPLOAD_DIR / "reports.7z", server.UPLOAD_DIR / "unpacked")

    assert [source["name"] for source in sources] == ["large.pdf"]
    assert prepared == ["large.pdf"]
    assert skipped == []


def test_archive_upload_skips_pdf_members_that_fail_to_parse(isolated_server, monkeypatch):
    server, _storage, _pool = isolated_server

    monkeypatch.setattr(server, "ARCHIVE_PDF_MAX_BYTES", 100)

    unreadable_pdf = server.UPLOAD_DIR / "unreadable.pdf"
    unreadable_pdf.write_bytes(b"%PDF-1.4 unreadable")

    def fake_extract_archive(path, destination_dir):
        return [unreadable_pdf]

    def fake_prepare_pdf_source(path, logger):
        raise ValueError("No tables found")

    monkeypatch.setattr(server, "_extract_pdf_members_from_archive", fake_extract_archive)
    monkeypatch.setattr(server, "prepare_pdf_source", fake_prepare_pdf_source)

    with pytest.raises(ValueError, match="No readable PDF tables found"):
        server._prepare_archive_pdf_sources(server.UPLOAD_DIR / "reports.7z", server.UPLOAD_DIR / "unpacked")


def test_upload_zip_rejects_archives_without_pdfs(isolated_server):
    server, _storage, _pool = isolated_server
    from fastapi.testclient import TestClient

    archive = BytesIO()
    with ZipFile(archive, "w") as zf:
        zf.writestr("notes.txt", "ignore me")
    archive.seek(0)

    response = TestClient(server.app).post(
        "/sources/upload",
        files={"file": ("reports.zip", archive.getvalue(), "application/zip")},
    )

    assert response.status_code == 400
    assert "No PDF files found" in response.json()["detail"]


def test_zip_extraction_skips_oversized_members_before_writing(isolated_server, monkeypatch):
    server, _storage, _pool = isolated_server

    monkeypatch.setattr(server, "ARCHIVE_PDF_MAX_BYTES", 10)
    archive = BytesIO()
    with ZipFile(archive, "w") as zf:
        zf.writestr("large.pdf", b"x" * 20)
        zf.writestr("small.pdf", b"x" * 5)
    archive.seek(0)
    archive_path = server.UPLOAD_DIR / "reports.zip"
    archive_path.write_bytes(archive.getvalue())
    destination = server.UPLOAD_DIR / "zip-size-check"

    paths = server._extract_pdf_members_from_zip(archive_path, destination)

    assert [path.name for path in paths] == ["small.pdf"]
    assert not (destination / "large.pdf").exists()


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


def test_unsupported_local_table_query_does_not_fall_through_to_mcp(isolated_server, tmp_path):
    server, storage, pool = isolated_server
    from fastapi.testclient import TestClient
    
    project = storage.create_project("Test Project")
    source_id = "src_timetable"
    csv_path = tmp_path / "timetable.csv"
    csv_path.write_text("class,teacher\n1A,Smith\n", encoding="utf-8")
    storage.upsert_source(
        source_id=source_id,
        name="timetable.xlsx",
        kind="excel",
        rows=10,
        schema_json='{"columns":[{"name":"class"},{"name":"teacher"}],"row_count":10}',
        origin={"type": "csv_memory", "path": str(csv_path)}
    )
    
    storage.upsert_mcp_connector(
        connector_id="rapidai",
        name="RapidAI",
        scope="global",
        transport="stdio",
        url=None,
        command="mcp-mysql-server",
        args=[],
        tools=[],
        status="connected",
        last_error=None,
        description="",
        generated_description=None,
        description_status="metadata"
    )
    
    chat = storage.create_chat()
    storage.update_chat_project(chat["id"], project["id"])



    
    client = TestClient(server.app)
    
    class DummyRouter:
        available = True
        def classify_intent(self, **kwargs):
            return {"intent_type": "unsupported", "route": "ambiguous"}, "dummy", {}            
    import backend.server
    backend.server.LLMRouter = lambda *a, **kw: DummyRouter()
    
    response = client.post("/query", json={
        "chat_id": chat["id"],
        "question": "infer from the table and produce time table",
        "source_ids": [source_id],
        "mode": "smart"
    })
    
    output = response.text
    assert "clarify" in output
    assert "I can only answer questions about the loaded source" in output
