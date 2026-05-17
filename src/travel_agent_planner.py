from __future__ import annotations

from src.travel_agent_models import AuditEvent, ItineraryItem, Offer, PlanResponse, TravelRequest, Trip
from src.travel_agent_security import risk_label


def plan_trip(request: TravelRequest, model_ready: bool = False) -> PlanResponse:
    risk = risk_label(request)
    nights = 2
    if request.return_date:
        nights = max(1, (request.return_date - request.depart_date).days)

    flight_price = _flight_price(request)
    hotel_price = 160 * nights
    trip = Trip(
        request=request,
        risk=risk,
        flight_offers=[
            Offer(
                kind="flight",
                title=f"{request.origin.upper()} to {request.destination}",
                provider="shared-unipro-planner",
                price_usd=flight_price,
                refundable=risk != "low",
                notes=["Planning estimate only; confirm live fares before booking."],
            )
        ],
        hotel_offers=[
            Offer(
                kind="hotel",
                title=f"Business-ready stay near {request.destination}",
                provider="shared-unipro-planner",
                price_usd=hotel_price,
                refundable=True,
                notes=["Includes Wi-Fi, breakfast, and flexible cancellation preference."],
            )
        ],
        itinerary=_itinerary(request, nights),
        policy_checks=_policy_checks(request, risk, flight_price + hotel_price),
        savings_suggestions=_savings_suggestions(request),
    )

    events = [
        AuditEvent(trip_id=trip.id, event_type="plan.created", message="Created travel plan in shared Unipro backend."),
        AuditEvent(trip_id=trip.id, event_type="risk.assessed", message=f"Risk classified as {risk}."),
    ]
    if model_ready:
        events.append(AuditEvent(trip_id=trip.id, event_type="llm.available", message="Shared Unipro model routing is configured."))

    return PlanResponse(
        trip=trip,
        risk=risk,
        user_message=(
            "Draft plan prepared from shared Unipro backend policy and pricing estimates. "
            "Confirm current provider availability before booking."
        ),
        audit_events=events,
    )


def _flight_price(request: TravelRequest) -> int:
    multiplier = {"economy": 1, "premium_economy": 1.35, "business": 2.4, "first": 3.5}[request.cabin]
    return int(420 * multiplier * request.travelers)


def _itinerary(request: TravelRequest, nights: int) -> list[ItineraryItem]:
    purpose = request.purpose or "trip goals"
    return [
        ItineraryItem(day=1, title="Arrival and orientation", details=f"Arrive in {request.destination}, check in, and review {purpose}."),
        ItineraryItem(day=2, title="Primary work block", details="Keep the core schedule focused, with buffer time for transit and preparation."),
        ItineraryItem(day=min(3, nights + 1), title="Wrap-up and return prep", details="Capture notes, confirm receipts, and prepare for departure."),
    ]


def _policy_checks(request: TravelRequest, risk: str, estimated_total: int) -> list[str]:
    checks = [f"Risk level: {risk}."]
    if request.budget_usd and estimated_total > request.budget_usd:
        checks.append("Estimated plan is above the stated budget and needs approval.")
    else:
        checks.append("Estimated plan is within the stated budget or no budget was supplied.")
    if request.cabin in {"business", "first"}:
        checks.append("Premium cabin requires policy approval.")
    return checks


def _savings_suggestions(request: TravelRequest) -> list[str]:
    suggestions = ["Compare nearby airports and flexible hotel cancellation windows before booking."]
    if request.cabin != "economy":
        suggestions.append("Check whether premium economy satisfies the travel policy at a lower fare.")
    if request.travelers > 1:
        suggestions.append("Coordinate travelers on the same fare family to reduce change complexity.")
    return suggestions
