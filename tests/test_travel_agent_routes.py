from datetime import date, timedelta

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
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", False)
    get_pool().connectors.clear()
    yield server, storage, get_pool()
    get_pool().connectors.clear()


def _payload() -> dict[str, object]:
    return {
        "origin": "SFO",
        "destination": "New York",
        "depart_date": str(date.today() + timedelta(days=21)),
        "return_date": str(date.today() + timedelta(days=25)),
        "travelers": 2,
        "cabin": "economy",
        "budget_usd": 2400,
        "purpose": "client meetings",
    }


def test_travel_agent_plan_runs_on_shared_backend_without_internal_details(isolated_server):
    server, _storage, _pool = isolated_server
    client = TestClient(server.app)

    response = client.post("/api/travel/agent/plan", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["risk"] == "low"
    assert body["trip"]["status"] == "draft"
    assert body["trip"]["request"]["origin"] == "SFO"
    assert body["trip"]["flight_offers"][0]["provider"] == "shared-unipro-planner"
    assert "live booking inventory" not in body["user_message"].lower()
    assert "shared Unipro backend" in body["user_message"]
    assert body["audit_events"]


def test_travel_agent_plan_rejects_invalid_return_dates(isolated_server):
    server, _storage, _pool = isolated_server
    client = TestClient(server.app)
    payload = _payload()
    payload["return_date"] = str(date.today() + timedelta(days=3))
    payload["depart_date"] = str(date.today() + timedelta(days=5))

    response = client.post("/api/travel/agent/plan", json=payload)

    assert response.status_code == 422


def test_travel_agent_stored_endpoints_require_login_when_auth_is_enabled(isolated_server, monkeypatch):
    server, _storage, _pool = isolated_server
    monkeypatch.setattr(server, "API_KEY", "test-api-key")
    monkeypatch.setattr(server, "JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", True)
    client = TestClient(server.app)

    assert client.get("/api/travel/trips").status_code == 401
    assert client.post("/api/travel/trips", json=_payload()).status_code == 401
    assert client.get("/api/travel/admin/summary").status_code == 401
    assert client.get("/api/travel/admin/audit").status_code == 401


def test_travel_agent_trip_persistence_uses_shared_storage(isolated_server):
    server, _storage, _pool = isolated_server
    client = TestClient(server.app)

    created = client.post("/api/travel/trips", json=_payload())
    assert created.status_code == 201
    trip = created.json()

    listed = client.get("/api/travel/trips")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == trip["id"]

    summary = client.get("/api/travel/admin/summary")
    assert summary.status_code == 200
    assert summary.json()["total_trips"] == 1
    assert summary.json()["draft_trips"] == 1

    audit = client.get("/api/travel/admin/audit")
    assert audit.status_code == 200
    assert audit.json()[0]["event_type"] == "trip.created"


def test_travel_agent_saved_audit_redacts_sensitive_text(isolated_server):
    _server, storage, _pool = isolated_server

    storage.save_travel_agent_audit_event(
        owner_id="legacy",
        event={
            "id": "audit_test",
            "trip_id": "trip_test",
            "event_type": "private.note",
            "message": "Traveler traveler@example.com passport A1234567 token sk-live-abcdef1234567890",
            "created_at": "2026-05-17T00:00:00+00:00",
        },
    )

    events = storage.list_travel_agent_audit_events(owner_id="legacy")
    assert events[0]["message"] == "Traveler [redacted-email] passport [redacted-id] token [redacted-token]"
