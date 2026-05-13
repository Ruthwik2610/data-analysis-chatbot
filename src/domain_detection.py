"""
Domain detection from database schema column names.

Inspects column names against signal sets to classify an uploaded data source
as a known domain (travel, education) or None for generic/unknown.
"""
from __future__ import annotations

from typing import Any

# ── Signal vocabularies ───────────────────────────────────────────────────────

TRAVEL_SIGNALS: frozenset[str] = frozenset({
    # Route / location
    "departure", "arrival", "origin", "destination", "route",
    "departure_airport", "arrival_airport", "depart_airport", "arrive_airport",
    # Flight / booking
    "airline", "airline_code", "carrier", "flight_number", "flight_no",
    "flight", "booking_ref", "pnr", "ticket", "ticket_number",
    "itinerary", "itinerary_id", "reservation", "confirmation",
    # Passenger / traveler
    "passenger", "pax", "traveler", "traveller", "guest",
    # Class / fare
    "cabin_class", "cabin", "fare", "fare_class", "service_class",
    "travel_class", "seat_class",
    # Journey details
    "layover", "stopover", "stops", "connection",
    "seat", "seat_number", "gate", "terminal",
    # Schedule
    "departure_date", "arrival_date", "travel_date", "check_in", "boarding",
    "departure_time", "arrival_time",
    # Airport / geography
    "airport", "iata", "iata_code", "icao",
    # Cost / budget
    "fare_amount", "ticket_price", "total_fare",
    # Extras
    "baggage", "luggage", "visa", "passport",
})

EDUCATION_SIGNALS: frozenset[str] = frozenset({
    "student", "student_id", "pupil", "learner",
    "course", "course_id", "subject", "class", "class_id",
    "grade", "grade_level", "gpa", "marks", "score",
    "semester", "term", "academic_year",
    "teacher", "instructor", "professor", "faculty",
    "curriculum", "enrollment", "attendance",
    "exam", "test", "assignment", "homework",
    "school", "college", "university", "department",
})

# Minimum number of matching signals to confirm a domain
MIN_SIGNALS = 3


# ── Core detection ────────────────────────────────────────────────────────────

def _extract_col_names(schema: dict[str, Any]) -> set[str]:
    """Return a set of lowercased, underscore-normalised column names."""
    cols: set[str] = set()
    for col in schema.get("columns", []):
        raw = col.get("name") or col.get("column") or ""
        if raw:
            normalised = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
            cols.add(normalised)
    return cols


def detect_domain(schema: dict[str, Any]) -> str | None:
    """Return the detected domain string or *None* for generic/unknown schemas.

    Args:
        schema: A ``{"columns": [{"name": ...}, ...]}`` dict as produced by
                the existing ``DataSource.schema`` field.

    Returns:
        ``"travel"``, ``"education"``, or ``None``.
    """
    cols = _extract_col_names(schema)
    if not cols:
        return None

    travel_hits = len(cols & TRAVEL_SIGNALS)
    education_hits = len(cols & EDUCATION_SIGNALS)

    if travel_hits >= MIN_SIGNALS and travel_hits >= education_hits:
        return "travel"
    if education_hits >= MIN_SIGNALS:
        return "education"
    return None


def domain_confidence(schema: dict[str, Any]) -> dict[str, float]:
    """Return a confidence score (0–1) for each candidate domain.

    Useful for logging / debugging which signals fired.
    """
    cols = _extract_col_names(schema)
    total = max(len(cols), 1)
    return {
        "travel": min(1.0, len(cols & TRAVEL_SIGNALS) / max(MIN_SIGNALS, 1)),
        "education": min(1.0, len(cols & EDUCATION_SIGNALS) / max(MIN_SIGNALS, 1)),
    }
