import json
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.storage import Storage

@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    return Storage(db_path)

def test_list_chats_hides_legacy_by_default_for_authenticated_users(storage):
    storage.create_chat(title="Legacy Chat", owner_id="legacy")
    user_id = "user_123"
    storage.create_chat(title="User Chat", owner_id=user_id)

    chats = storage.list_chats(owner_id=user_id)
    titles = [c["title"] for c in chats]

    assert "User Chat" in titles
    assert "Legacy Chat" not in titles
    assert len(chats) == 1


def test_list_chats_can_include_legacy_for_test_user(storage):
    storage.create_chat(title="Legacy Chat", owner_id="legacy")
    user_id = "user_123"
    storage.create_chat(title="User Chat", owner_id=user_id)

    chats = storage.list_chats(owner_id=user_id, include_legacy=True)
    titles = [c["title"] for c in chats]

    assert "User Chat" in titles
    assert "Legacy Chat" in titles
    assert len(chats) == 2

def test_list_chats_only_legacy_for_legacy_owner(storage):
    storage.create_chat(title="Legacy Chat", owner_id="legacy")
    user_id = "user_123"
    storage.create_chat(title="User Chat", owner_id=user_id)

    chats = storage.list_chats(owner_id="legacy")
    titles = [c["title"] for c in chats]
    
    assert "Legacy Chat" in titles
    assert "User Chat" not in titles
    assert len(chats) == 1

def test_create_and_list_projects(storage):
    storage.create_project(title="Project A", owner_id="user_1")
    storage.create_project(title="Project B", owner_id="user_1")
    storage.create_project(title="Project C", owner_id="user_2")
    
    user1_projects = storage.list_projects(owner_id="user_1")
    assert len(user1_projects) == 2
    titles = [p["title"] for p in user1_projects]
    assert "Project A" in titles
    assert "Project B" in titles
    
    user2_projects = storage.list_projects(owner_id="user_2")
    assert len(user2_projects) == 1
    assert user2_projects[0]["title"] == "Project C"

def test_project_title_uniqueness(storage):
    storage.create_project(title="Unique Project", owner_id="user_1")
    with pytest.raises(ValueError, match="A project with this name already exists"):
        storage.create_project(title="Unique Project", owner_id="user_1")
    
    # Different owner can have same title (if intended, though usually titles are globally unique in some systems, 
    # but here it's filtered by owner_id in project_title_exists)
    storage.create_project(title="Unique Project", owner_id="user_2")


def test_create_travel_journey_persists_downloaded_itinerary_with_hotel(storage):
    intent = {
        "origin": "HYD",
        "destination": "RUH",
        "departure_date": "2026-06-01",
        "return_date": "2026-06-08",
        "passengers": 1,
        "cabin_class": "economy",
    }
    flight_offer = {
        "offer_id": "flight_123",
        "airline": "United",
        "price_usd": 750,
        "currency": "USD",
    }
    hotel_offer = {
        "hotel_id": "hotel_456",
        "name": "Riyadh Suites",
        "total_price": 900,
        "currency": "USD",
    }

    journey = storage.create_travel_journey(
        owner_id="user_123",
        chat_id=None,
        intent=intent,
        offer=flight_offer,
        hotel_offer=hotel_offer,
        status="downloaded",
    )

    assert journey["id"].startswith("journey_")
    assert journey["status"] == "downloaded"
    assert journey["downloaded_at"] is not None
    assert journey["total_price_usd"] == 1650
    assert journey["currency"] == "USD"
    assert journey["flight_offer"] == flight_offer
    assert journey["hotel_offer"] == hotel_offer

    rows = storage.list_travel_journeys(owner_id="user_123")
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "downloaded"
    assert row["downloaded_at"] is not None
    assert row["total_price_usd"] == 1650
    assert row["currency"] == "USD"
    assert row["flight_offer_json"] == json.dumps(flight_offer)
    assert row["hotel_offer_json"] == json.dumps(hotel_offer)


def test_create_travel_journey_uses_normalized_non_usd_hotel_total(storage):
    flight_offer = {
        "offer_id": "flight_123",
        "price_usd": 750,
        "currency": "USD",
    }
    hotel_offer = {
        "hotel_id": "hotel_456",
        "total_price": 900,
        "total_price_usd": 990,
        "currency": "EUR",
    }

    journey = storage.create_travel_journey(
        owner_id="user_123",
        chat_id=None,
        intent={"origin": "HYD", "destination": "RUH"},
        offer=flight_offer,
        hotel_offer=hotel_offer,
        status="downloaded",
    )

    assert journey["total_price_usd"] == 1740
    assert storage.list_travel_journeys(owner_id="user_123")[0]["total_price_usd"] == 1740


def test_post_journeys_saves_downloaded_itinerary_with_hotel(monkeypatch, tmp_path):
    import backend.server as server

    storage = Storage(tmp_path / "app.sqlite")
    monkeypatch.setattr(server, "DB", storage)
    monkeypatch.setattr(server, "API_KEY", "")
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", False)
    monkeypatch.setattr(server, "_current_user_id", lambda request: "user_123")
    client = TestClient(server.app)

    intent = {
        "origin": "HYD",
        "destination": "RUH",
        "departure_date": "2026-06-01",
        "return_date": "2026-06-08",
        "passengers": 1,
        "cabin_class": "economy",
    }
    flight_offer = {
        "offer_id": "flight_123",
        "airline": "United",
        "price_usd": 750,
        "currency": "USD",
    }
    hotel_offer = {
        "hotel_id": "hotel_456",
        "name": "Riyadh Suites",
        "total_price": 900,
        "currency": "USD",
    }

    response = client.post(
        "/api/journeys",
        json={
            "intent": intent,
            "offer": flight_offer,
            "hotel_offer": hotel_offer,
            "status": "downloaded",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("journey_")
    assert body["status"] == "downloaded"
    assert body["downloaded_at"] is not None
    assert body["total_price_usd"] == 1650
    assert body["currency"] == "USD"
    assert body["flight_offer"] == flight_offer
    assert body["hotel_offer"] == hotel_offer

    rows = storage.list_travel_journeys(owner_id="user_123")
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "downloaded"
    assert row["downloaded_at"] is not None
    assert row["total_price_usd"] == 1650
    assert row["currency"] == "USD"
    assert row["flight_offer_json"] == json.dumps(flight_offer)
    assert row["hotel_offer_json"] == json.dumps(hotel_offer)


def test_post_journeys_rejects_invalid_status(monkeypatch, tmp_path):
    import backend.server as server

    storage = Storage(tmp_path / "app.sqlite")
    monkeypatch.setattr(server, "DB", storage)
    monkeypatch.setattr(server, "API_KEY", "")
    monkeypatch.setattr(server, "USER_AUTH_REQUIRED", False)
    monkeypatch.setattr(server, "_current_user_id", lambda request: "user_123")
    client = TestClient(server.app)

    response = client.post(
        "/api/journeys",
        json={
            "intent": {"origin": "HYD", "destination": "RUH"},
            "offer": {"offer_id": "flight_123", "price_usd": 750, "currency": "USD"},
            "status": "booked",
        },
    )

    assert response.status_code == 422
    assert storage.list_travel_journeys(owner_id="user_123") == []
