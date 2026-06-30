from __future__ import annotations

import pytest

from src.currency import convert_money, normalize_currency


def test_normalize_currency_accepts_clean_iso_codes():
    assert normalize_currency("usd") == "USD"
    assert normalize_currency(" AED ") == "AED"


def test_normalize_currency_rejects_unknown_or_invalid_codes():
    assert normalize_currency("DOGE") is None
    assert normalize_currency("US") is None
    assert normalize_currency(None) is None


def test_convert_money_uses_builtin_rates_without_network():
    converted = convert_money(367.25, "AED", "USD", use_live=False)
    assert converted is not None
    assert converted.amount == pytest.approx(100.0, abs=0.01)
    assert converted.currency == "USD"
    assert converted.rate == pytest.approx(1 / 3.6725)
    assert converted.source == "builtin"


def test_convert_money_returns_original_amount_for_same_currency():
    converted = convert_money(125, "usd", "USD", use_live=False)
    assert converted is not None
    assert converted.amount == 125
    assert converted.rate == 1.0
