from __future__ import annotations

import re
from datetime import date

from src.travel_agent_models import Risk, TravelRequest


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
API_KEY_RE = re.compile(r"\b(?:sk|pk|api|key|token)[-_]?[A-Za-z0-9][A-Za-z0-9._-]{12,}\b", re.IGNORECASE)
PASSPORT_RE = re.compile(r"\b[A-Z][0-9]{7,8}\b")


def redact_sensitive_text(text: str) -> str:
    redacted = EMAIL_RE.sub("[redacted-email]", text)
    redacted = BEARER_RE.sub("[redacted-token]", redacted)
    redacted = API_KEY_RE.sub("[redacted-token]", redacted)
    redacted = PASSPORT_RE.sub("[redacted-id]", redacted)
    return redacted


def public_error_message(_exc: Exception) -> str:
    return "We could not complete that request safely. Please try again."


def risk_label(request: TravelRequest) -> Risk:
    score = 0
    destination = request.destination.lower()
    international_hint = "," in destination or any(
        marker in destination
        for marker in (" japan", " france", " india", " london", " tokyo", " paris", " mexico", " canada")
    )
    if international_hint:
        score += 1
    if request.cabin in {"business", "first"}:
        score += 1
    if (request.depart_date - date.today()).days <= 7:
        score += 1

    estimated_total = _estimated_total(request)
    if request.budget_usd and estimated_total > request.budget_usd:
        score += 1

    if score >= 3:
        return "high"
    if score >= 1:
        return "medium"
    return "low"


def _estimated_total(request: TravelRequest) -> int:
    nights = 2
    if request.return_date:
        nights = max(1, (request.return_date - request.depart_date).days)
    cabin_multiplier = {"economy": 1, "premium_economy": 1.35, "business": 2.4, "first": 3.5}[request.cabin]
    flight = int(420 * cabin_multiplier * request.travelers)
    hotel = 180 * nights
    return flight + hotel
