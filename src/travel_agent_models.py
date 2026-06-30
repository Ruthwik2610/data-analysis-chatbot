from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


Cabin = Literal["economy", "premium_economy", "business", "first"]
Risk = Literal["low", "medium", "high"]
TripStatus = Literal["draft", "submitted", "booked", "cancelled"]


class TravelRequest(BaseModel):
    origin: str = Field(..., min_length=2, max_length=80)
    destination: str = Field(..., min_length=2, max_length=120)
    depart_date: date
    return_date: date | None = None
    travelers: int = Field(default=1, ge=1, le=9)
    cabin: Cabin = "economy"
    budget_usd: int | None = Field(default=None, ge=1)
    purpose: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_dates(self) -> "TravelRequest":
        if self.return_date and self.return_date < self.depart_date:
            raise ValueError("return_date must be on or after depart_date")
        return self


class Offer(BaseModel):
    id: str = Field(default_factory=lambda: f"offer_{uuid4().hex[:12]}")
    kind: Literal["flight", "hotel"]
    title: str
    provider: str
    price_usd: int
    currency: str = "USD"
    refundable: bool = False
    notes: list[str] = Field(default_factory=list)


class ItineraryItem(BaseModel):
    day: int = Field(..., ge=1)
    title: str
    details: str


class Trip(BaseModel):
    id: str = Field(default_factory=lambda: f"trip_{uuid4().hex[:12]}")
    request: TravelRequest
    status: TripStatus = "draft"
    risk: Risk = "low"
    flight_offers: list[Offer] = Field(default_factory=list)
    hotel_offers: list[Offer] = Field(default_factory=list)
    itinerary: list[ItineraryItem] = Field(default_factory=list)
    policy_checks: list[str] = Field(default_factory=list)
    savings_suggestions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"audit_{uuid4().hex[:12]}")
    trip_id: str | None = None
    event_type: str
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AdminSummary(BaseModel):
    total_trips: int
    draft_trips: int
    booked_trips: int
    high_risk_trips: int
    audit_events: int


class PlanResponse(BaseModel):
    trip: Trip
    risk: Risk
    user_message: str
    audit_events: list[AuditEvent]
