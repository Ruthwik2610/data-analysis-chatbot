from fastapi.testclient import TestClient
import pytest
from dataclasses import replace


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
    if hasattr(server, "JWT_SECRET"):
        monkeypatch.setattr(server, "JWT_SECRET", "test-secret")
    get_pool().connectors.clear()
    yield server, storage, get_pool()
    get_pool().connectors.clear()


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_user_jwt_scopes_projects_chats_and_sources(isolated_server, monkeypatch):
    server, storage, _pool = isolated_server
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", True)
    monkeypatch.setattr(server, "API_KEY", "shared-api-key")
    monkeypatch.setattr(server, "JWT_SECRET", "test-secret")
    client = TestClient(server.app)

    alice = _register(client, "alice@example.com")
    bob = _register(client, "bob@example.com")

    alice_project = client.post("/projects", json={"title": "Sales"}, headers=_headers(alice)).json()
    bob_project = client.post("/projects", json={"title": "Ops"}, headers=_headers(bob)).json()

    alice_chat = storage.create_chat("Alice chat", owner_id=storage.get_user_by_email("alice@example.com")["id"])
    bob_chat = storage.create_chat("Bob chat", owner_id=storage.get_user_by_email("bob@example.com")["id"])
    storage.update_chat_project(alice_chat["id"], alice_project["id"], owner_id=storage.get_user_by_email("alice@example.com")["id"])
    storage.update_chat_project(bob_chat["id"], bob_project["id"], owner_id=storage.get_user_by_email("bob@example.com")["id"])
    storage.upsert_source(
        source_id="src_alice",
        name="alice.csv",
        kind="csv",
        rows=1,
        schema_json="{}",
        origin=None,
        owner_id=storage.get_user_by_email("alice@example.com")["id"],
    )
    storage.upsert_source(
        source_id="src_bob",
        name="bob.csv",
        kind="csv",
        rows=1,
        schema_json="{}",
        origin=None,
        owner_id=storage.get_user_by_email("bob@example.com")["id"],
    )

    assert [p["id"] for p in client.get("/projects", headers=_headers(alice)).json()] == [alice_project["id"]]
    assert [c["id"] for c in client.get(f"/chats?project_id={alice_project['id']}", headers=_headers(alice)).json()] == [alice_chat["id"]]
    assert [s["id"] for s in client.get("/sources", headers=_headers(alice)).json()] == ["src_alice"]

    assert client.get(f"/projects/{bob_project['id']}", headers=_headers(alice)).status_code == 404
    assert client.get(f"/chats/{bob_chat['id']}", headers=_headers(alice)).status_code == 404
    assert client.get("/projects", headers={"Authorization": "Bearer shared-api-key"}).status_code == 401


def test_regular_authenticated_user_cannot_see_legacy_chats(isolated_server, monkeypatch):
    server, storage, _pool = isolated_server
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", True)
    monkeypatch.setattr(server, "API_KEY", "shared-api-key")
    monkeypatch.setattr(server, "JWT_SECRET", "test-secret")
    client = TestClient(server.app)
    token = _register(client, "alice@example.com")
    legacy_chat = storage.create_chat("Legacy chat", owner_id="legacy")

    response = client.get("/chats?project_id=none", headers=_headers(token))

    assert response.status_code == 200
    assert response.json() == []
    assert client.get(f"/chats/{legacy_chat['id']}", headers=_headers(token)).status_code == 404


def test_configured_test_user_can_see_legacy_chats(isolated_server, monkeypatch):
    server, storage, _pool = isolated_server
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", True)
    monkeypatch.setattr(server, "API_KEY", "shared-api-key")
    monkeypatch.setattr(server, "JWT_SECRET", "test-secret")
    monkeypatch.setattr(server, "TEST_USER_EMAIL", "sample-test-user@example.com")
    client = TestClient(server.app)
    token = _register(client, "sample-test-user@example.com")
    legacy_chat = storage.create_chat("Legacy chat", owner_id="legacy")

    response = client.get("/chats?project_id=none", headers=_headers(token))

    assert response.status_code == 200
    assert [chat["id"] for chat in response.json()] == [legacy_chat["id"]]
    assert client.get(f"/chats/{legacy_chat['id']}", headers=_headers(token)).status_code == 200


def test_displayed_test_user_credentials_can_login_and_see_legacy_chats(isolated_server, monkeypatch):
    server, storage, _pool = isolated_server
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", True)
    monkeypatch.setattr(server, "API_KEY", "shared-api-key")
    monkeypatch.setattr(server, "JWT_SECRET", "test-secret")
    monkeypatch.setattr(server, "TEST_USER_EMAIL", "sample-test-user@example.com")
    monkeypatch.setattr(server, "TEST_USER_PASSWORD", "sample-public-test-password")
    client = TestClient(server.app)
    legacy_chat = storage.create_chat("Legacy chat", owner_id="legacy")

    login = client.post("/auth/login", json={"email": "sample-test-user@example.com", "password": "sample-public-test-password"})

    assert login.status_code == 200
    assert login.json()["user"]["email"] == "sample-test-user@example.com"
    chats = client.get("/chats?project_id=none", headers=_headers(login.json()["access_token"]))
    assert [chat["id"] for chat in chats.json()] == [legacy_chat["id"]]


def test_regular_user_token_does_not_open_admin_session(isolated_server, monkeypatch):
    server, _storage, _pool = isolated_server
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", True)
    monkeypatch.setattr(server, "API_KEY", "shared-api-key")
    monkeypatch.setattr(server, "JWT_SECRET", "test-secret")
    monkeypatch.setattr(server, "CONFIG", replace(server.CONFIG, admin_password="admin-secret"))
    client = TestClient(server.app)
    user_token = _register(client, "tester@example.com")

    assert client.get("/admin/session", headers=_headers(user_token)).status_code == 401
    assert client.get("/admin/session", headers={"x-admin-token": "bad"}).status_code == 401

    admin_login = client.post("/admin/login", json={"password": "admin-secret"})
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["token"]
    assert client.get("/admin/session", headers={"x-admin-token": admin_token}).json() == {
        "ok": True,
        "role": "admin",
    }


def test_project_titles_are_unique_per_user(isolated_server, monkeypatch):
    server, _storage, _pool = isolated_server
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", True)
    monkeypatch.setattr(server, "API_KEY", "shared-api-key")
    monkeypatch.setattr(server, "JWT_SECRET", "test-secret")
    client = TestClient(server.app)
    token = _register(client, "alice@example.com")

    first = client.post("/projects", json={"title": "Sales Book"}, headers=_headers(token))
    duplicate = client.post("/projects", json={"title": " sales book "}, headers=_headers(token))

    assert first.status_code == 200
    assert duplicate.status_code == 409


def test_project_cannot_link_same_source_twice(isolated_server, monkeypatch):
    server, storage, _pool = isolated_server
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", True)
    monkeypatch.setattr(server, "API_KEY", "shared-api-key")
    monkeypatch.setattr(server, "JWT_SECRET", "test-secret")
    client = TestClient(server.app)
    token = _register(client, "alice@example.com")
    user_id = storage.get_user_by_email("alice@example.com")["id"]
    project = client.post("/projects", json={"title": "Sales Book"}, headers=_headers(token)).json()
    storage.upsert_source(
        source_id="src_sales",
        name="sales.csv",
        kind="csv",
        rows=1,
        schema_json="{}",
        origin=None,
        owner_id=user_id,
    )

    first = client.post(
        f"/projects/{project['id']}/files",
        json={"source_id": "src_sales"},
        headers=_headers(token),
    )
    duplicate = client.post(
        f"/projects/{project['id']}/files",
        json={"source_id": "src_sales"},
        headers=_headers(token),
    )

    assert first.status_code == 200
    assert duplicate.status_code == 409
