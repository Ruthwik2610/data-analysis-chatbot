from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


_BUILTIN_RATES_PER_USD: dict[str, float] = {
    "USD": 1.0,
    "AED": 3.6725,
    "AUD": 1.52,
    "CAD": 1.36,
    "CHF": 0.91,
    "EUR": 0.92,
    "GBP": 0.79,
    "INR": 83.0,
    "JPY": 156.0,
    "QAR": 3.64,
    "SAR": 3.75,
    "SGD": 1.34,
    "ZAR": 18.5,
}
_CACHE_TTL_SECONDS = 60 * 60 * 12
_rate_cache: dict[tuple[str, str], tuple[float, float]] = {}


@dataclass(frozen=True)
class MoneyConversion:
    amount: float
    currency: str
    rate: float
    source: str


def normalize_currency(code: Any) -> str | None:
    if code is None:
        return None
    normalized = str(code).strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        return None
    if normalized not in _BUILTIN_RATES_PER_USD:
        return None
    return normalized


def convert_money(
    amount: float | int | str | None,
    from_currency: Any,
    to_currency: Any = "USD",
    *,
    use_live: bool = True,
) -> MoneyConversion | None:
    source = normalize_currency(from_currency)
    target = normalize_currency(to_currency)
    if source is None or target is None:
        return None
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        return None
    if source == target:
        return MoneyConversion(amount=value, currency=target, rate=1.0, source="identity")

    rate: float | None = None
    rate_source = "builtin"
    if use_live:
        rate = _live_rate(source, target)
        if rate is not None:
            rate_source = "frankfurter"
    if rate is None:
        rate = _builtin_rate(source, target)
    if rate is None:
        return None
    return MoneyConversion(
        amount=round(value * rate, 2),
        currency=target,
        rate=rate,
        source=rate_source,
    )


def _builtin_rate(source: str, target: str) -> float | None:
    source_per_usd = _BUILTIN_RATES_PER_USD.get(source)
    target_per_usd = _BUILTIN_RATES_PER_USD.get(target)
    if not source_per_usd or not target_per_usd:
        return None
    return target_per_usd / source_per_usd


def _live_rate(source: str, target: str) -> float | None:
    now = time.time()
    cache_key = (source, target)
    cached = _rate_cache.get(cache_key)
    if cached and now - cached[1] < _CACHE_TTL_SECONDS:
        return cached[0]
    query = urllib.parse.urlencode({"base": source, "symbols": target})
    url = f"https://api.frankfurter.dev/v1/latest?{query}"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rate = float(payload.get("rates", {}).get(target))
    except Exception:
        return None
    _rate_cache[cache_key] = (rate, now)
    return rate
