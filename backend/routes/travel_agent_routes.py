from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.travel_agent_models import AdminSummary, AuditEvent, PlanResponse, TravelRequest, Trip
from src.travel_agent_planner import plan_trip
from src.travel_agent_security import public_error_message


router = APIRouter(prefix="/api/travel", tags=["Travel Agent"])


def _shared_model_ready() -> bool:
    from backend.server import CONFIG, MODEL_PRESETS

    return bool(CONFIG.openrouter_api_key and MODEL_PRESETS.get("flash", {}).get("model"))


def _owner_id(request: Request) -> str:
    from backend.server import _current_user_id

    return _current_user_id(request)


@router.post("/agent/plan", response_model=PlanResponse)
def create_plan(request_body: TravelRequest) -> PlanResponse:
    try:
        return plan_trip(request_body, model_ready=_shared_model_ready())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=public_error_message(exc)) from exc


@router.get("/trips", response_model=list[Trip])
def list_trips(request: Request) -> list[Trip]:
    from backend.server import DB

    return [Trip.model_validate(trip) for trip in DB.list_travel_agent_trips(owner_id=_owner_id(request))]


@router.post("/trips", response_model=Trip, status_code=status.HTTP_201_CREATED)
def create_trip(request_body: TravelRequest, request: Request) -> Trip:
    from backend.server import DB

    response = plan_trip(request_body, model_ready=_shared_model_ready())
    events = response.audit_events + [
        AuditEvent(trip_id=response.trip.id, event_type="trip.created", message="Trip draft saved in shared Unipro backend.")
    ]
    saved = DB.save_travel_agent_trip(
        owner_id=_owner_id(request),
        trip=response.trip.model_dump(mode="json"),
        events=[event.model_dump(mode="json") for event in events],
    )
    return Trip.model_validate(saved)


@router.get("/admin/summary", response_model=AdminSummary)
def admin_summary(request: Request) -> AdminSummary:
    from backend.server import DB

    return AdminSummary.model_validate(DB.travel_agent_admin_summary(owner_id=_owner_id(request)))


@router.get("/admin/audit", response_model=list[AuditEvent])
def admin_audit(request: Request) -> list[AuditEvent]:
    from backend.server import DB

    return [AuditEvent.model_validate(event) for event in DB.list_travel_agent_audit_events(owner_id=_owner_id(request))]
