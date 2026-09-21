"""Unit tests for manual forex trade calculations."""

import pytest

from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
    get_forex_instrument,
)
from app.trades.service import TradeService
from app.utils.errors import ValidationError
from app.utils.trade_fingerprint import build_trade_fingerprint


def _instrument(pair: str) -> dict:
    instrument = get_forex_instrument(
        pair,
        symbol_mappings=get_default_symbol_mappings(),
    )
    assert instrument is not None
    return instrument


def test_eur_usd_one_lot_calculates_pips_and_usd_pnl():
    result = TradeService._calculate_forex_trade(
        {
            "lot_size": 1,
            "entry_price": 1.10000,
            "exit_price": 1.10150,
            "side": "Long",
        },
        _instrument("EUR/USD"),
    )

    assert result["pips"] == 15
    assert result["native_pnl"] == 150
    assert result["usd_pnl"] == 150
    assert result["pip_value_per_standard_lot"] == 10


def test_usd_jpy_keeps_native_quote_currency_pnl():
    result = TradeService._calculate_forex_trade(
        {
            "lot_size": 0.1,
            "entry_price": 150.000,
            "exit_price": 150.250,
            "side": "Long",
            "quote_to_usd_rate": 0.0067,
        },
        _instrument("USD/JPY"),
    )

    assert result["pips"] == 25
    assert result["native_pnl"] == 2500
    assert result["native_pnl_currency"] == "JPY"
    assert result["usd_pnl"] == pytest.approx(16.75)


def test_gbp_eur_uses_supplied_quote_conversion_rate():
    instrument = {
        "base_currency": "GBP",
        "quote_currency": "EUR",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000,
    }
    result = TradeService._calculate_forex_trade(
        {
            "lot_size": 0.5,
            "entry_price": 1.17000,
            "exit_price": 1.17100,
            "side": "Long",
            "quote_to_usd_rate": 1.08,
        },
        instrument,
    )

    assert result["pips"] == 10
    assert result["native_pnl"] == 50
    assert result["usd_pnl"] == pytest.approx(54)


def test_short_trade_is_directionally_symmetric():
    long_result = TradeService._calculate_forex_trade(
        {
            "lot_size": 1,
            "entry_price": 1.10000,
            "exit_price": 1.10100,
            "side": "Long",
        },
        _instrument("EUR/USD"),
    )
    short_result = TradeService._calculate_forex_trade(
        {
            "lot_size": 1,
            "entry_price": 1.10100,
            "exit_price": 1.10000,
            "side": "Short",
        },
        _instrument("EUR/USD"),
    )

    assert short_result["pips"] == long_result["pips"]
    assert short_result["usd_pnl"] == long_result["usd_pnl"]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "lot_size": 0.0009,
            "entry_price": 1.10000,
            "exit_price": 1.10100,
            "side": "Long",
        },
        {
            "lot_size": 1,
            "entry_price": 1.100001,
            "exit_price": 1.10100,
            "side": "Long",
        },
        {
            "lot_size": 1,
            "entry_price": 1.10000,
            "exit_price": 1.10100,
            "side": "Long",
            "quote_to_usd_rate": 2,
        },
    ],
)
def test_forex_entry_rejects_invalid_lot_or_price_inputs(payload):
    with pytest.raises(ValidationError):
        TradeService._calculate_forex_trade(
            payload,
            _instrument("EUR/USD"),
        )


def test_fractional_lots_are_preserved_in_trade_fingerprints():
    common = {
        "source": "manual",
        "symbol": "EUR/USD",
        "side": "Long",
        "entry_time": "2026-01-01T10:00:00+00:00",
        "exit_time": "2026-01-01T10:05:00+00:00",
        "avg_entry_price": 1.1,
        "avg_exit_price": 1.101,
    }

    first = build_trade_fingerprint({**common, "total_quantity": 0.1})
    second = build_trade_fingerprint({**common, "total_quantity": 0.01})

    assert first != second
