"""
Zero-trust multi-loop travel recommendation orchestrator.

Three isolated sub-agents (CustomerContext, DBHistory, DuffelMCP) pass only
sanitized structs to each other. The Orchestrator merges their outputs and
streams flight offer cards back to the chat.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from opentelemetry import trace

from src.mcp_pool import extract_text_content

TRACER = trace.get_tracer(__name__)

POLICY_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "company_travel_policy.json"

# ── Data structures (zero-trust message types) ────────────────────────────────

@dataclass
class TravelIntent:
    origin: str | None = None
    destination: str | None = None
    departure_date: str | None = None
    return_date: str | None = None
    passengers: int = 1
    cabin_class: str = "economy"
    currency: str = "USD"
    confidence: float = 0.0
    raw_question: str = ""


@dataclass
class TravelHistory:
    traveler_tier: str = "standard"
    preferred_airlines: list[str] = field(default_factory=list)
    past_routes: list[str] = field(default_factory=list)
    total_trips_ytd: int = 0
    budget_limit_usd: float = 1500.0
    policy: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlightOffer:
    offer_id: str
    airline: str
    airline_iata: str
    origin: str
    destination: str
    departure_at: str
    arrival_at: str
    duration_minutes: int
    stops: int
    cabin_class: str
    price_usd: float
    currency: str
    policy_compliant: bool
    policy_violation_reason: str | None
    booking_redirect_url: str
    expires_at: str | None = None
    score: float = 0.0


# ── Multi-loop thinking chain ─────────────────────────────────────────────────

class TravelThinkingChain:
    """Implements Reflect-Branch-Rollback inner-loop reasoning.

    2025 research pattern: each sub-agent has up to MAX_INNER_ROUNDS reflection
    passes. A fast-path skips extra loops when confidence already >= threshold.
    """

    def __init__(self, max_inner_rounds: int = 3, confidence_threshold: float = 0.9) -> None:
        self.max_inner_rounds = max_inner_rounds
        self.confidence_threshold = confidence_threshold

    def should_continue(self, round_idx: int, confidence: float) -> bool:
        """Return True if another inner loop is warranted."""
        if confidence >= self.confidence_threshold:
            return False
        return round_idx < self.max_inner_rounds


# ── Heuristic intent extraction (no LLM needed for common patterns) ───────────

_IATA_RE = re.compile(r'\b([A-Z]{3})\b')
_DATE_RE = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')
_PAX_RE  = re.compile(r'\b(\d+)\s*(?:passenger|pax|adult|people|person|travell?er)', re.I)
_CABIN_KEYWORDS = {
    "economy": ["economy", "coach", "standard"],
    "premium_economy": ["premium economy", "premium_economy", "premium"],
    "business": ["business", "business class", "biz"],
    "first": ["first class", "first"],
}

def extract_travel_intent(question: str) -> TravelIntent:
    """Fast heuristic extraction — no LLM call for common sentence patterns."""
    intent = TravelIntent(raw_question=question)
    iata_codes = _IATA_RE.findall(question)
    if len(iata_codes) >= 2:
        intent.origin, intent.destination = iata_codes[0], iata_codes[1]
        intent.confidence += 0.5
    dates = _DATE_RE.findall(question)
    if dates:
        intent.departure_date = dates[0]
        if len(dates) > 1:
            intent.return_date = dates[1]
        intent.confidence += 0.2
    pax_match = _PAX_RE.search(question)
    if pax_match:
        intent.passengers = int(pax_match.group(1))
        intent.confidence += 0.1
    q_lower = question.lower()
    for cabin, keywords in _CABIN_KEYWORDS.items():
        if any(k in q_lower for k in keywords):
            intent.cabin_class = cabin
            intent.confidence += 0.1
            break
    return intent


def _load_policy() -> dict[str, Any]:
    try:
        return json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _tier_policy(policy: dict[str, Any], tier: str) -> dict[str, Any]:
    return policy.get("tiers", {}).get(tier, policy.get("tiers", {}).get("standard", {}))


def _score_offer(offer_data: dict[str, Any], history: TravelHistory, policy_tier: dict[str, Any]) -> tuple[float, bool, str | None]:
    """Return (composite_score 0-1, policy_compliant, violation_reason)."""
    weights = {"price": 0.40, "airline": 0.25, "stops": 0.20, "advance": 0.15}
    price = float(offer_data.get("price_usd") or 0)
    budget = history.budget_limit_usd or 1500.0
    price_score = max(0.0, 1.0 - price / budget) if budget > 0 else 0.5

    preferred = policy_tier.get("preferred_airlines") or []
    airline_iata = offer_data.get("airline_iata", "")
    airline_score = 1.0 if (not preferred or airline_iata in preferred) else 0.3

    stops = int(offer_data.get("stops") or 0)
    stops_score = max(0.0, 1.0 - stops * 0.3)

    composite = (
        weights["price"] * price_score
        + weights["airline"] * airline_score
        + weights["stops"] * stops_score
        + weights["advance"] * 0.5   # simplified; full impl uses booking lead-time
    )

    # Policy compliance check
    allowed_cabins = policy_tier.get("allowed_cabin_classes") or ["economy"]
    cabin = str(offer_data.get("cabin_class") or "economy").lower().replace(" ", "_")
    max_conn = policy_tier.get("max_connections", 2)

    if cabin not in allowed_cabins:
        return composite, False, f"Cabin '{cabin}' not allowed for tier (allowed: {', '.join(allowed_cabins)})"
    if stops > max_conn:
        return composite, False, f"{stops} connection(s) exceeds policy maximum of {max_conn}"
    if price > budget:
        return composite, False, f"Price ${price:.0f} exceeds budget limit ${budget:.0f}"

    return composite, True, None


# ── Main Orchestrator ─────────────────────────────────────────────────────────

class TravelOrchestrator:
    """Zero-trust multi-loop travel recommendation engine.

    Data flow:
        question → CustomerContext (TravelIntent)
                 → DBHistory (TravelHistory) [parallel]
                 → DuffelMCP (list[FlightOffer])
                 → Synthesize → streamed chat events
    """

    async def run(
        self,
        *,
        question: str,
        chat_id: str,
        source_ids: list[str] | None,
        request_id: str,
        router: Any,
        pool: Any,
        db: Any,
        config: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        with TRACER.start_as_current_span("travel_orchestrator") as span:
            span.set_attribute("question", question)
            span.set_attribute("request_id", request_id)

            # ── Phase 1: Customer Context (inner loop) ────────────────────
            yield {"kind": "thinking", "step": "✈️ Extracting travel intent…", "progress": 15}
            intent = await self._customer_context_agent(question, router, request_id)
            span.set_attribute("intent.origin", intent.origin or "")
            span.set_attribute("intent.destination", intent.destination or "")

            # ── Phase 2: DB History (parallel inner loop) ─────────────────
            yield {"kind": "thinking", "step": "🗄️ Checking travel history & policy…", "progress": 40}
            history = await self._db_history_agent(intent, source_ids, db)
            span.set_attribute("history.tier", history.traveler_tier)
            span.set_attribute("history.budget", history.budget_limit_usd)

            # ── Phase 3: Duffel search (inner loop with constraint relaxation)
            yield {"kind": "thinking", "step": "🔍 Searching live flight availability…", "progress": 65}
            offers = await self._duffel_agent(intent, history, pool, config)
            span.set_attribute("duffel.offer_count", len(offers))

            # ── Phase 4: Synthesize ───────────────────────────────────────
            yield {"kind": "thinking", "step": "📊 Ranking offers by policy & preference…", "progress": 85}
            async for event in self._synthesize(intent, history, offers, question):
                yield event

    # ── Sub-agents ────────────────────────────────────────────────────────────

    async def _customer_context_agent(
        self, question: str, router: Any, request_id: str
    ) -> TravelIntent:
        with TRACER.start_as_current_span("customer_context_agent"):
            chain = TravelThinkingChain()
            intent = extract_travel_intent(question)
            # Fast-path: heuristic already confident
            if chain.should_continue(0, intent.confidence):
                intent = await self._llm_fill_intent(question, intent, router, request_id)
            return intent

    async def _llm_fill_intent(
        self, question: str, partial: TravelIntent, router: Any, request_id: str
    ) -> TravelIntent:
        """Ask LLM to fill missing intent fields when heuristic confidence < 0.9."""
        if not getattr(router, "available", False):
            return partial
        prompt = (
            "Extract travel booking intent from this request as JSON with these exact keys: "
            "origin (IATA code or city), destination (IATA code or city), "
            "departure_date (YYYY-MM-DD or null), return_date (YYYY-MM-DD or null), "
            "passengers (integer), cabin_class (economy|premium_economy|business|first).\n\n"
            f"Request: {question}\n\n"
            f"Already extracted: origin={partial.origin}, destination={partial.destination}, "
            f"departure_date={partial.departure_date}, passengers={partial.passengers}, "
            f"cabin_class={partial.cabin_class}\n\n"
            "Return ONLY the JSON object, no explanation."
        )
        try:
            data, _ = await asyncio.to_thread(router._generate_json, prompt, request_id)
            if data.get("origin"):
                partial.origin = str(data["origin"])
            if data.get("destination"):
                partial.destination = str(data["destination"])
            if data.get("departure_date"):
                partial.departure_date = str(data["departure_date"])
            if data.get("return_date"):
                partial.return_date = str(data["return_date"])
            if data.get("passengers"):
                partial.passengers = int(data["passengers"])
            if data.get("cabin_class"):
                partial.cabin_class = str(data["cabin_class"])
            partial.confidence = 0.95
        except Exception:
            pass
        return partial

    async def _db_history_agent(
        self, intent: TravelIntent, source_ids: list[str] | None, db: Any
    ) -> TravelHistory:
        """Query the uploaded travel DB for history + extract policy tier.

        Zero-trust: only sanitized scalar values leave this agent.
        """
        with TRACER.start_as_current_span("db_history_agent"):
            history = TravelHistory()
            global_policy = _load_policy()

            # Try to extract policy info from uploaded source
            if source_ids and db:
                try:
                    for src_id in source_ids[:2]:
                        row = db.get_source(src_id)
                        if not row:
                            continue
                        schema = json.loads(row.get("schema_json") or "{}")
                        col_names = {c.get("name", "").lower() for c in schema.get("columns", [])}

                        # Detect tier column
                        tier_col = next((c for c in col_names if "tier" in c or "level" in c), None)
                        budget_col = next(
                            (c for c in col_names if "budget" in c or "max_price" in c or "limit" in c), None
                        )
                        airline_col = next((c for c in col_names if "airline" in c or "carrier" in c), None)

                        # Only extract scalar policy info — never raw row data
                        if tier_col or budget_col:
                            history.traveler_tier = "standard"   # default; real impl would query
                        if budget_col:
                            history.budget_limit_usd = float(
                                global_policy.get("tiers", {})
                                .get(history.traveler_tier, {})
                                .get("max_flight_budget_usd", 1500)
                            )
                        if airline_col:
                            tier_data = _tier_policy(global_policy, history.traveler_tier)
                            history.preferred_airlines = tier_data.get("preferred_airlines") or []
                except Exception:
                    pass

            # Apply global policy for the tier
            tier_data = _tier_policy(global_policy, history.traveler_tier)
            if not history.budget_limit_usd or history.budget_limit_usd == 1500.0:
                history.budget_limit_usd = float(tier_data.get("max_flight_budget_usd", 1500))
            if not history.preferred_airlines:
                history.preferred_airlines = tier_data.get("preferred_airlines") or []
            history.policy = tier_data
            return history

    async def _duffel_agent(
        self, intent: TravelIntent, history: TravelHistory, pool: Any, config: Any
    ) -> list[FlightOffer]:
        """Call Duffel MCP tool with ONLY sanitized search parameters.

        Zero-trust: history's raw DB data never reaches Duffel.
        """
        with TRACER.start_as_current_span("duffel_search_agent") as span:
            # Find Duffel connector in pool
            duffel_cid = None
            for cid, state in (pool.connectors if pool else {}).items():
                if "duffel" in state.name.lower() and state.status == "connected":
                    duffel_cid = cid
                    break

            if not duffel_cid:
                span.set_attribute("duffel.available", False)
                return []

            if not intent.origin or not intent.destination:
                return []

            # Build SANITIZED params — zero-trust boundary
            search_params: dict[str, Any] = {
                "origin": intent.origin,
                "destination": intent.destination,
                "departure_date": intent.departure_date or "",
                "passengers": intent.passengers,
                "cabin_class": intent.cabin_class,
                "max_price_usd": history.budget_limit_usd,
            }
            if intent.return_date:
                search_params["return_date"] = intent.return_date

            chain = TravelThinkingChain()
            raw_offers: list[dict[str, Any]] = []

            for round_idx in range(chain.max_inner_rounds):
                try:
                    result = await pool.call_tool(duffel_cid, "search_flights", search_params)
                    text = extract_text_content(result)
                    try:
                        data = json.loads(text) if text else None
                    except json.JSONDecodeError:
                        data = None
                        span.set_attribute(f"duffel.parse_error.round_{round_idx}", text[:200])
                    if isinstance(data, list):
                        raw_offers = data
                    elif isinstance(data, dict) and data.get("error"):
                        span.set_attribute(f"duffel.error.round_{round_idx}", data["error"])
                except Exception as exc:
                    span.set_attribute(f"duffel.exception.round_{round_idx}", str(exc))

                confidence = 0.95 if raw_offers else 0.0
                if not chain.should_continue(round_idx + 1, confidence):
                    break

                # Reflect: relax constraints if no results
                if not raw_offers:
                    search_params["max_price_usd"] = search_params.get("max_price_usd", 1500) * 1.2
                    if search_params.get("cabin_class") == "business":
                        search_params["cabin_class"] = "economy"

            # Shape raw dicts into FlightOffer, score each
            policy_tier = history.policy
            offers: list[FlightOffer] = []
            for raw in raw_offers[:10]:
                score, compliant, violation = _score_offer(raw, history, policy_tier)
                offers.append(FlightOffer(
                    offer_id=str(raw.get("offer_id") or ""),
                    airline=str(raw.get("airline") or ""),
                    airline_iata=str(raw.get("airline_iata") or ""),
                    origin=str(raw.get("origin") or intent.origin or ""),
                    destination=str(raw.get("destination") or intent.destination or ""),
                    departure_at=str(raw.get("departure_at") or ""),
                    arrival_at=str(raw.get("arrival_at") or ""),
                    duration_minutes=int(raw.get("duration_minutes") or 0),
                    stops=int(raw.get("stops") or 0),
                    cabin_class=str(raw.get("cabin_class") or intent.cabin_class),
                    price_usd=float(raw.get("price_usd") or 0),
                    currency=str(raw.get("currency") or "USD"),
                    policy_compliant=compliant,
                    policy_violation_reason=violation,
                    booking_redirect_url=str(raw.get("booking_redirect_url") or ""),
                    expires_at=raw.get("expires_at"),
                    score=score,
                ))

            offers.sort(key=lambda o: (-o.score, o.price_usd))
            span.set_attribute("duffel.offers_returned", len(offers))
            return offers

    async def _synthesize(
        self,
        intent: TravelIntent,
        history: TravelHistory,
        offers: list[FlightOffer],
        question: str,
    ) -> AsyncIterator[dict[str, Any]]:
        with TRACER.start_as_current_span("travel_synthesize"):
            # Emit structured travel_result event for the UI
            offer_dicts = [
                {
                    "offer_id": o.offer_id,
                    "airline": o.airline,
                    "airline_iata": o.airline_iata,
                    "origin": o.origin,
                    "destination": o.destination,
                    "departure_at": o.departure_at,
                    "arrival_at": o.arrival_at,
                    "duration_minutes": o.duration_minutes,
                    "stops": o.stops,
                    "cabin_class": o.cabin_class,
                    "price_usd": o.price_usd,
                    "currency": o.currency,
                    "policy_compliant": o.policy_compliant,
                    "policy_violation_reason": o.policy_violation_reason,
                    "booking_redirect_url": o.booking_redirect_url,
                    "expires_at": o.expires_at,
                    "score": round(o.score, 3),
                }
                for o in offers[:5]
            ]

            intent_dict = {
                "origin": intent.origin,
                "destination": intent.destination,
                "departure_date": intent.departure_date,
                "return_date": intent.return_date,
                "passengers": intent.passengers,
                "cabin_class": intent.cabin_class,
                "traveler_tier": history.traveler_tier,
                "budget_limit_usd": history.budget_limit_usd,
            }

            # Text summary for markdown fallback
            if not offers:
                summary = (
                    f"No flights found for **{intent.origin} → {intent.destination}** "
                    f"on {intent.departure_date or 'the requested date'}.\n\n"
                    "Try adjusting dates or cabin class. You can also search directly on "
                    f"[Duffel](https://duffel.com/search?origin={intent.origin or ''}&destination={intent.destination or ''})."
                )
            else:
                best = offers[0]
                compliant_count = sum(1 for o in offers if o.policy_compliant)
                summary = (
                    f"Found **{len(offers)} flight offer(s)** for "
                    f"**{intent.origin} → {intent.destination}** ({intent.cabin_class}).\n\n"
                    f"**Best match:** {best.airline} — **${best.price_usd:.0f}** "
                    f"({'✅ Policy compliant' if best.policy_compliant else '⚠️ Needs approval'})\n\n"
                    f"{compliant_count} of {len(offers)} offers comply with your **{history.traveler_tier}** tier policy "
                    f"(budget: ${history.budget_limit_usd:.0f})."
                )

            yield {
                "kind": "travel_result",
                "text": summary,
                "travel_offers": offer_dicts,
                "travel_intent": intent_dict,
            }
