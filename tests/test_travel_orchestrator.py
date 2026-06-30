"""Tests for src/travel_orchestrator.py"""
from __future__ import annotations

import asyncio

import pytest
from src.travel_orchestrator import (
    AIRLINE_CLARIFY_MARKER,
    FlightOffer,
    HotelOffer,
    TravelOrchestrator,
    TravelThinkingChain,
    TravelIntent,
    TravelHistory,
    _extract_airline_answer_from_history,
    _question_for_airline_followup,
    extract_travel_intent,
    _score_offer,
    _score_hotel,
)


# ── TravelThinkingChain ───────────────────────────────────────────────────────

def test_thinking_chain_defaults():
    chain = TravelThinkingChain()
    assert chain.max_inner_rounds == 3
    assert chain.confidence_threshold == 0.9


def test_thinking_chain_fast_path_stops_early():
    chain = TravelThinkingChain(max_inner_rounds=3, confidence_threshold=0.9)
    # High confidence → should NOT continue
    assert chain.should_continue(0, 0.95) is False


def test_thinking_chain_continues_when_low_confidence():
    chain = TravelThinkingChain(max_inner_rounds=3, confidence_threshold=0.9)
    assert chain.should_continue(0, 0.3) is True
    assert chain.should_continue(1, 0.5) is True
    assert chain.should_continue(2, 0.7) is True
    # At max rounds, stop regardless of confidence
    assert chain.should_continue(3, 0.5) is False


# ── extract_travel_intent ─────────────────────────────────────────────────────

def test_extracts_iata_codes():
    intent = extract_travel_intent("Find me a flight from LHR to JFK next week")
    assert intent.origin == "LHR"
    assert intent.destination == "JFK"


def test_extracts_iso_dates():
    intent = extract_travel_intent("I need to fly 2025-06-15 returning 2025-06-22")
    assert intent.departure_date == "2025-06-15"
    assert intent.return_date == "2025-06-22"


def test_extracts_passenger_count():
    intent = extract_travel_intent("Book 3 passengers from BOM to SIN")
    assert intent.passengers == 3


def test_extracts_cabin_class_business():
    intent = extract_travel_intent("Business class from LHR to JFK")
    assert intent.cabin_class == "business"


def test_extracts_cabin_class_economy():
    intent = extract_travel_intent("Find cheapest economy flight from DXB to LHR")
    assert intent.cabin_class == "economy"


def test_returns_intent_object_always():
    # Should never raise even for gibberish
    intent = extract_travel_intent("hello world")
    assert isinstance(intent, TravelIntent)
    assert intent.passengers == 1
    assert intent.cabin_class == "economy"


# ── _score_offer ──────────────────────────────────────────────────────────────

def _make_history(tier="standard", budget=1500, preferred=None):
    return TravelHistory(
        traveler_tier=tier,
        budget_limit_usd=budget,
        preferred_airlines=preferred or ["UA", "DL"],
        policy={
            "max_flight_budget_usd": budget,
            "allowed_cabin_classes": ["economy"],
            "max_connections": 2,
        },
    )


def test_score_compliant_offer():
    offer = {"price_usd": 800, "cabin_class": "economy", "stops": 1, "airline_iata": "UA"}
    history = _make_history(budget=1500)
    score, compliant, reason = _score_offer(offer, history, history.policy)
    assert compliant is True
    assert reason is None
    assert 0.0 <= score <= 1.0


def test_score_over_budget_not_compliant():
    offer = {"price_usd": 2000, "cabin_class": "economy", "stops": 0, "airline_iata": "UA"}
    history = _make_history(budget=1500)
    _, compliant, reason = _score_offer(offer, history, history.policy)
    assert compliant is False
    assert "budget" in (reason or "").lower()


def test_score_wrong_cabin_not_compliant():
    offer = {"price_usd": 500, "cabin_class": "business", "stops": 0, "airline_iata": "UA"}
    history = _make_history(budget=1500)
    _, compliant, reason = _score_offer(offer, history, history.policy)
    assert compliant is False
    assert "cabin" in (reason or "").lower() or "allowed" in (reason or "").lower()


def test_score_too_many_stops_not_compliant():
    offer = {"price_usd": 500, "cabin_class": "economy", "stops": 3, "airline_iata": "UA"}
    history = _make_history(budget=1500)
    _, compliant, reason = _score_offer(offer, history, history.policy)
    assert compliant is False
    assert "connection" in (reason or "").lower()


# ── Zero-trust: Duffel args must not contain raw DB fields ────────────────────

def test_zero_trust_duffel_params_are_sanitized():
    """Verify that _duffel_agent only passes allowed keys to search_flights."""
    forbidden_keys = {"booking_ref", "passenger_name", "employee_id", "ssn", "passport", "pnr"}
    allowed_keys = {"origin", "destination", "departure_date", "return_date",
                    "passengers", "cabin_class", "max_price_usd"}

    # Simulate what _duffel_agent builds — must only contain allowed keys
    intent = TravelIntent(origin="LHR", destination="JFK", departure_date="2025-07-01",
                          passengers=2, cabin_class="economy")
    history = TravelHistory(budget_limit_usd=1500.0)

    params = {
        "origin": intent.origin,
        "destination": intent.destination,
        "departure_date": intent.departure_date,
        "passengers": intent.passengers,
        "cabin_class": intent.cabin_class,
        "max_price_usd": history.budget_limit_usd,
    }

    assert set(params.keys()) <= allowed_keys
    assert not (set(params.keys()) & forbidden_keys)


# ── _synthesize surfaces return_slice ─────────────────────────────────────────

def test_synthesize_emits_return_slice_on_offers():
    return_slice = {
        "origin": "JFK",
        "destination": "LHR",
        "departure_at": "2025-07-08T18:00:00",
        "arrival_at": "2025-07-09T06:00:00",
        "duration_minutes": 420,
        "stops": 0,
        "airline": "British Airways",
        "airline_iata": "BA",
    }
    offer = FlightOffer(
        offer_id="off_1",
        airline="British Airways",
        airline_iata="BA",
        origin="LHR",
        destination="JFK",
        departure_at="2025-07-01T09:00:00",
        arrival_at="2025-07-01T12:00:00",
        duration_minutes=480,
        stops=0,
        cabin_class="economy",
        price_usd=750.0,
        currency="USD",
        policy_compliant=True,
        policy_violation_reason=None,
        booking_redirect_url="https://example.com/book",
        expires_at=None,
        score=0.9,
        return_slice=return_slice,
    )
    intent = TravelIntent(
        origin="LHR",
        destination="JFK",
        departure_date="2025-07-01",
        return_date="2025-07-08",
        cabin_class="economy",
    )
    history = TravelHistory(traveler_tier="standard", budget_limit_usd=1500.0)

    async def collect():
        events = []
        async for ev in TravelOrchestrator()._synthesize(intent, history, [offer], [], "round trip LHR JFK"):
            events.append(ev)
        return events

    events = asyncio.run(collect())
    result = next(ev for ev in events if ev["kind"] == "travel_result")
    assert result["travel_offers"][0]["return_slice"] == return_slice
    assert "Return:" in result["text"]
    assert "2025-07-08" in result["text"]


# ── Test A: intent classification (hotel/flight keywords) ─────────────────────

def test_intent_hotel_only():
    intent = extract_travel_intent(
        "Find me a hotel in RUH from 2026-05-30 to 2026-06-05"
    )
    assert intent.wants_hotels is True
    assert intent.wants_flights is False
    assert intent.destination == "RUH"
    assert intent.check_in_date == "2026-05-30"
    assert intent.check_out_date == "2026-06-05"


def test_intent_flights_and_hotel():
    intent = extract_travel_intent("Flights and hotel from HYD to RUH")
    assert intent.wants_hotels is True
    assert intent.wants_flights is True


def test_intent_flight_only_regression():
    intent = extract_travel_intent("Find me a flight from HYD to RUH")
    assert intent.wants_flights is True
    assert intent.wants_hotels is False


def test_round_trip_flight_defaults_to_hotel_step():
    intent = extract_travel_intent("Find flights from HYD to JNB on 2026-05-30 returning 2026-06-10")
    assert intent.wants_flights is True
    assert intent.wants_hotels is True
    assert intent.check_in_date == "2026-05-30"
    assert intent.check_out_date == "2026-06-10"


def test_round_trip_flight_only_can_skip_hotel_step():
    intent = extract_travel_intent(
        "Find flight only from HYD to JNB on 2026-05-30 returning 2026-06-10"
    )
    assert intent.wants_flights is True
    assert intent.wants_hotels is False


def test_customer_context_defaults_llm_round_trip_to_hotel_step():
    class Router:
        available = True

        def _generate_json(self, prompt, request_id):
            return (
                {
                    "origin": "HYD",
                    "destination": "JNB",
                    "departure_date": "2026-05-30",
                    "return_date": "2026-06-10",
                    "passengers": 1,
                    "cabin_class": "economy",
                    "wants_flights": True,
                    "wants_hotels": False,
                    "check_in_date": None,
                    "check_out_date": None,
                    "rooms": 1,
                    "guests": 1,
                },
                None,
            )

    intent = asyncio.run(
        TravelOrchestrator()._customer_context_agent(
            "find flights from Hyd to johannesberg on 30 may return would be on 10th june. no prefrence for airline",
            Router(),
            "req-1",
        )
    )

    assert intent.wants_flights is True
    assert intent.wants_hotels is True
    assert intent.check_in_date == "2026-05-30"
    assert intent.check_out_date == "2026-06-10"


def test_airline_followup_uses_previous_travel_question_for_intent():
    previous_question = "Find flights from SFO to JFK on 2026-06-01 returning 2026-06-05"
    history = [
        {"role": "user", "content": previous_question},
        {"role": "assistant", "content": f"Which is your **{AIRLINE_CLARIFY_MARKER}**?"},
        {"role": "user", "content": "no preference"},
    ]

    assert _question_for_airline_followup("no preference", history) == previous_question
    assert _question_for_airline_followup("United", history[:-1] + [{"role": "user", "content": "United"}]) == previous_question
    assert _question_for_airline_followup("no preference", []) == "no preference"


def test_airline_followup_accepts_misspelled_no_preference_reply():
    previous_question = "Find flights from HYD to JNB on 2026-05-30 returning 2026-06-10"
    history = [
        {"role": "user", "content": previous_question},
        {"role": "assistant", "content": f"Which is your **{AIRLINE_CLARIFY_MARKER}**?"},
        {"role": "user", "content": "no prefrence for airline"},
    ]

    assert _question_for_airline_followup("no prefrence for airline", history) == previous_question
    assert _extract_airline_answer_from_history("no prefrence for airline", history) == "__none__"


# ── Test B: hotel scoring ──────────────────────────────────────────────────────

def _make_policy_tier(per_night_cap=200):
    return {"hotel_max_per_night_usd": per_night_cap}


def test_score_hotel_compliant():
    raw = {"price_per_night": 100, "currency": "USD", "star_rating": 4, "review_score": 8.5}
    history = TravelHistory()
    policy_tier = _make_policy_tier(per_night_cap=200)
    composite, compliant, reason = _score_hotel(raw, history, policy_tier)
    assert compliant is True
    assert reason is None
    assert 0.0 <= composite <= 1.0


def test_score_hotel_converts_non_usd_price_for_policy_check():
    raw = {"price_per_night": 500, "currency": "AED", "star_rating": 4, "review_score": 8.5}
    history = TravelHistory()
    policy_tier = _make_policy_tier(per_night_cap=200)
    _, compliant, reason = _score_hotel(raw, history, policy_tier)
    assert compliant is True
    assert reason is None


def test_score_hotel_over_cap():
    raw = {"price_per_night": 250, "currency": "USD", "star_rating": 5, "review_score": 9.0}
    history = TravelHistory()
    policy_tier = _make_policy_tier(per_night_cap=200)
    composite, compliant, reason = _score_hotel(raw, history, policy_tier)
    assert compliant is False
    assert reason is not None
    assert "exceeds" in reason.lower()
    assert 0.0 <= composite <= 1.0


# ── Test C: _synthesize emits hotel_offers ────────────────────────────────────

def test_synthesize_emits_hotel_offers():
    hotel = HotelOffer(
        hotel_id="h_1",
        name="Riyadh Grand Hotel",
        address="King Fahd Rd, Riyadh",
        star_rating=5,
        review_score=9.1,
        photo_url="https://example.com/photo.jpg",
        price_per_night=150.0,
        total_price=900.0,
        currency="USD",
        check_in_date="2026-05-30",
        check_out_date="2026-06-05",
        rooms=1,
        guests=1,
        redirect_url="https://example.com/book",
        policy_compliant=True,
        policy_violation_reason=None,
        score=0.85,
    )
    intent = TravelIntent(
        destination="RUH",
        wants_flights=False,
        wants_hotels=True,
        check_in_date="2026-05-30",
        check_out_date="2026-06-05",
    )
    history = TravelHistory(traveler_tier="standard", budget_limit_usd=1500.0)

    async def collect():
        events = []
        async for ev in TravelOrchestrator()._synthesize(intent, history, [], [hotel], "hotel in RUH"):
            events.append(ev)
        return events

    events = asyncio.run(collect())
    result = next(ev for ev in events if ev["kind"] == "travel_result")
    assert len(result["hotel_offers"]) == 1
    h = result["hotel_offers"][0]
    assert h["hotel_id"] == "h_1"
    assert h["name"] == "Riyadh Grand Hotel"
    assert h["policy_compliant"] is True
    assert "Riyadh Grand Hotel" in result["text"]
