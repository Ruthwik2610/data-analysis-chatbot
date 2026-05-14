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
from datetime import date, timedelta
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
    date_assumed: bool = False
    duffel_offline: bool = False
    airline_filter_applied: bool = False
    airline_fallback_to_all: bool = False


@dataclass
class TravelHistory:
    traveler_tier: str = "standard"
    preferred_airlines: list[str] = field(default_factory=list)
    past_routes: list[str] = field(default_factory=list)
    total_trips_ytd: int = 0
    budget_limit_usd: float = 1500.0
    policy: dict[str, Any] = field(default_factory=dict)
    # User-chosen airline preference for THIS trip (from Excel column or follow-up answer).
    # Distinct from policy-level `preferred_airlines`.
    user_preferred_airline: str | None = None


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


# Marker phrase included in the airline-clarify message. The orchestrator
# detects this in the previous assistant message to treat the user's next
# reply as the airline answer. Keep wording stable.
AIRLINE_CLARIFY_MARKER = "preferred airline for this trip"

# ── Heuristic intent extraction (no LLM needed for common patterns) ───────────

_IATA_RE = re.compile(r'\b([A-Z]{3})\b')
_DATE_RE = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')
_PAX_RE  = re.compile(r'\b(\d+)\s*(?:passenger|pax|adult|people|person|travell?er)', re.I)
_AIRLINE_COL_RE = re.compile(r'(?i)(preferred|favorite|favourite|fav)[\s_]*(airline|carrier)')
_NO_PREF_RE = re.compile(r'(?i)\b(no preference|no preferred|none|skip|any airline|any carrier|doesn.?t matter|don.?t care)\b')
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


def _extract_preferred_airline_from_dfs(dataframes: list[Any]) -> str | None:
    """Scan loaded DataFrames for a preferred-airline column, return most common value.

    Looks for columns matching `(preferred|favorite|favourite)[ _]?(airline|carrier)`
    (case-insensitive). Returns the most common non-null string value across matched
    columns, or None if nothing matched or all values are empty.
    """
    for df in dataframes:
        if df is None:
            continue
        try:
            cols = [str(c) for c in getattr(df, "columns", [])]
        except Exception:
            continue
        matched = [c for c in cols if _AIRLINE_COL_RE.search(c)]
        for col in matched:
            try:
                series = df[col].dropna().astype(str).str.strip()
                series = series[series != ""]
                if series.empty:
                    continue
                # Most common value — handles datasets where the user has logged
                # multiple trips with the same favorite airline.
                top = series.value_counts().idxmax()
                if top and isinstance(top, str):
                    return top
            except Exception:
                continue
    return None


def _extract_airline_answer_from_history(
    current_question: str, chat_history: list[dict[str, Any]]
) -> str | None:
    """If the previous assistant message was an airline clarify, parse the current reply.

    Returns:
        - airline name string (e.g. "Emirates")
        - "__none__" sentinel if the user explicitly said no preference
        - None if there was no recent airline clarify to answer
    """
    last_assistant: str | None = None
    for msg in reversed(chat_history):
        role = (msg.get("role") or "").lower()
        if role == "assistant":
            last_assistant = str(msg.get("content") or "")
            break
        if role == "user":
            # The current question is the most recent user turn; anything older
            # is irrelevant context. Continue scanning for the assistant turn
            # that came just before it.
            continue
    if not last_assistant or AIRLINE_CLARIFY_MARKER not in last_assistant:
        return None
    reply = current_question.strip()
    if not reply:
        return None
    if _NO_PREF_RE.search(reply):
        return "__none__"
    # Take the first short phrase as the airline name. Strip prompt-y words.
    cleaned = re.sub(r'(?i)^(yes|ok|sure|please|i prefer|i like|my preferred|prefer|use)\s+', '', reply)
    cleaned = re.sub(r'(?i)\b(airlines?|carrier)\b', '', cleaned).strip()
    # Cap to 40 chars to avoid passing a full sentence as the filter.
    return cleaned[:40] if cleaned else None


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
        dataframes: list[Any] | None = None,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        with TRACER.start_as_current_span("travel_orchestrator") as span:
            span.set_attribute("question", question)
            span.set_attribute("request_id", request_id)

            # ── Phase 1: Customer Context (inner loop) ────────────────────
            yield {"kind": "thinking", "step": "✈️ Extracting travel intent…", "progress": 15}
            intent = await self._customer_context_agent(question, router, request_id)
            span.set_attribute("intent.origin", intent.origin or "")
            span.set_attribute("intent.destination", intent.destination or "")

            # Early-exit if we still can't parse origin / destination as IATA codes.
            # Without this, Duffel returns nothing and the user sees a generic
            # "No flights found for None → None" string.
            if not intent.origin or not intent.destination:
                yield {
                    "kind": "travel_result",
                    "text": (
                        "I couldn't pin down a clear origin and destination from your question. "
                        "Try naming the cities or 3-letter airport codes — for example "
                        "`flights from HYD to RUH on 2026-05-30 returning 2026-06-05`."
                    ),
                    "travel_offers": [],
                    "travel_intent": {
                        "origin": intent.origin,
                        "destination": intent.destination,
                        "departure_date": intent.departure_date,
                        "return_date": intent.return_date,
                        "passengers": intent.passengers,
                        "cabin_class": intent.cabin_class,
                    },
                }
                return

            # ── Phase 2: DB History (parallel inner loop) ─────────────────
            yield {"kind": "thinking", "step": "🗄️ Checking travel history & policy…", "progress": 40}
            history = await self._db_history_agent(intent, source_ids, db, dataframes)
            span.set_attribute("history.tier", history.traveler_tier)
            span.set_attribute("history.budget", history.budget_limit_usd)
            span.set_attribute("history.user_pref_airline", history.user_preferred_airline or "")

            # ── Phase 2b: Airline preference resolution ───────────────────
            # If no preference came from uploaded sources, check whether the
            # user just answered a prior clarify (chat_history-driven), then
            # otherwise emit a clarify and stop.
            if not history.user_preferred_airline:
                from_history = _extract_airline_answer_from_history(question, chat_history or [])
                if from_history == "__none__":
                    history.user_preferred_airline = None  # user explicitly said no preference
                elif from_history:
                    history.user_preferred_airline = from_history
                else:
                    # First time we hit this question for this trip — ask.
                    yield {
                        "kind": "travel_clarify",
                        "content": (
                            f"Before I search, which is your **{AIRLINE_CLARIFY_MARKER}**? "
                            "Type an airline name (e.g. `Emirates`, `IndiGo`, `Air India`) "
                            "or `no preference` to see all carriers."
                        ),
                    }
                    return

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
        today_iso = date.today().isoformat()
        prompt = (
            "Extract travel booking intent from this request as JSON with these exact keys: "
            "origin (the 3-letter IATA airport code, uppercase, e.g. HYD for Hyderabad; "
            "if the user named a city or country, return the primary international airport's IATA code), "
            "destination (same rules as origin), "
            "departure_date (strict YYYY-MM-DD; resolve natural-language dates like "
            "\"30 may 2026\" or \"next Friday\" to the absolute date; "
            f"today is {today_iso}; if year is missing, assume the next occurrence on or after today), "
            "return_date (same rules as departure_date, or null for one-way), "
            "passengers (positive integer, default 1), "
            "cabin_class (one of: economy, premium_economy, business, first).\n\n"
            f"Request: {question}\n\n"
            f"Already extracted: origin={partial.origin}, destination={partial.destination}, "
            f"departure_date={partial.departure_date}, passengers={partial.passengers}, "
            f"cabin_class={partial.cabin_class}\n\n"
            "Return ONLY the JSON object, no explanation. Use null for any field you cannot determine."
        )
        iata_re = re.compile(r"^[A-Z]{3}$")
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        try:
            data, _ = await asyncio.to_thread(router._generate_json, prompt, request_id)
            origin = str(data.get("origin") or "").strip().upper()
            if iata_re.match(origin):
                partial.origin = origin
            dest = str(data.get("destination") or "").strip().upper()
            if iata_re.match(dest):
                partial.destination = dest
            dep = str(data.get("departure_date") or "").strip()
            if date_re.match(dep):
                partial.departure_date = dep
            ret = str(data.get("return_date") or "").strip()
            if date_re.match(ret):
                partial.return_date = ret
            if data.get("passengers"):
                try:
                    partial.passengers = max(1, int(data["passengers"]))
                except (TypeError, ValueError):
                    pass
            cabin = str(data.get("cabin_class") or "").strip().lower()
            if cabin in {"economy", "premium_economy", "business", "first"}:
                partial.cabin_class = cabin
            partial.confidence = 0.95
        except Exception:
            pass
        return partial

    async def _db_history_agent(
        self,
        intent: TravelIntent,
        source_ids: list[str] | None,
        db: Any,
        dataframes: list[Any] | None = None,
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

            # Detect user's preferred airline from uploaded dataframes.
            # Look for columns matching (preferred|favorite|favourite)[ _]?(airline|carrier).
            if dataframes:
                history.user_preferred_airline = _extract_preferred_airline_from_dfs(dataframes)
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
                intent.duffel_offline = True
                return []

            if not intent.origin or not intent.destination:
                return []

            if not intent.departure_date:
                intent.departure_date = (date.today() + timedelta(days=7)).isoformat()
                intent.date_assumed = True
                span.set_attribute("duffel.date_defaulted", intent.departure_date)

            # Build SANITIZED params — zero-trust boundary
            search_params: dict[str, Any] = {
                "origin": intent.origin,
                "destination": intent.destination,
                "departure_date": intent.departure_date,
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

            # Filter by user's preferred airline if set. Falls back to showing
            # all offers (with a banner) when nothing matches the carrier.
            pref = (history.user_preferred_airline or "").strip()
            if pref and offers:
                pref_low = pref.lower()
                # Exact IATA match (2-3 letters, all alphanum) is more precise
                # than substring; otherwise compare against airline display name.
                is_iata = len(pref) <= 3 and pref.isalpha()
                if is_iata:
                    filtered = [o for o in offers if o.airline_iata.upper() == pref.upper()]
                else:
                    filtered = [o for o in offers if pref_low in o.airline.lower()]
                if filtered:
                    offers = filtered
                    intent.airline_filter_applied = True
                else:
                    intent.airline_fallback_to_all = True
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

            assumed_note = (
                f"*Assumed departure date {intent.departure_date} (a week from today). "
                "Tell me a specific date and I'll re-run the search.*\n\n"
                if intent.date_assumed else ""
            )

            # Text summary for markdown fallback
            if not offers:
                if intent.duffel_offline:
                    summary = (
                        "The Duffel flight-search bridge is offline right now, so I couldn't "
                        "look up live availability. Reconnect the Duffel MCP from the connector "
                        "panel (plug icon) and try again."
                    )
                else:
                    summary = (
                        f"{assumed_note}"
                        f"No flights returned for **{intent.origin} → {intent.destination}** "
                        f"on {intent.departure_date} in {intent.cabin_class}. "
                        "Try a different date, cabin class, or nearby airports."
                    )
            else:
                best = offers[0]
                compliant_count = sum(1 for o in offers if o.policy_compliant)
                pref = history.user_preferred_airline
                if intent.airline_filter_applied and pref:
                    pref_note = f"*Filtered to your preferred airline: **{pref}**.*\n\n"
                elif intent.airline_fallback_to_all and pref:
                    route_label = f"{intent.origin} → {intent.destination}"
                    pref_note = (
                        f"*No **{pref}** flights on this route ({route_label}) "
                        f"on {intent.departure_date} — showing all available options.*\n\n"
                    )
                else:
                    pref_note = ""
                trip_kind = "round-trip" if intent.return_date else "one-way"
                date_line = (
                    f"on {intent.departure_date} → returning {intent.return_date}"
                    if intent.return_date else f"on {intent.departure_date}"
                )
                summary = (
                    f"{assumed_note}"
                    f"{pref_note}"
                    f"Found **{len(offers)} flight offer(s)** for "
                    f"**{intent.origin} → {intent.destination}** {date_line} "
                    f"({trip_kind}, {intent.cabin_class}).\n\n"
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
