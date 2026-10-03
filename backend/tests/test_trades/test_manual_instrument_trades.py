"""Focused tests for Settings-driven manual trade sizing and conversion."""

from datetime import datetime, timezone

import pytest

from app.trades.conversion_rates import ManualTradeConversionRateService
from app.trades.service import TradeService
from app.utils.errors import ValidationError


def _stock_instrument() -> dict:
    return {
        "base_currency": "AAPL.US",
        "quote_currency": "USD",
        "quote_currency_unit_scale": 1,
        "pip_size": 0.01,
        "tick_size": 0.25,
        "price_precision": 2,
        "contract_size": 1,
        "min_lots": 1,
        "lot_increment": 1,
        "supported_for_simulation": True,
    }


def test_mapped_stock_lot_calculates_pnl_per_share():
    result = TradeService._calculate_mapped_instrument_trade(
        {
            "lot_size": 1,
            "entry_price": 100,
            "exit_price": 100.25,
            "side": "Long",
            "quote_to_usd_rate": 1,
        },
        _stock_instrument(),
    )

    assert result["lot_size"] == 1
    assert result["native_pnl"] == pytest.approx(0.25)
    assert result["usd_pnl"] == pytest.approx(0.25)
    assert result["native_pnl_currency"] == "USD"


def test_mapped_non_usd_trade_converts_quote_currency_pnl():
    result = TradeService._calculate_mapped_instrument_trade(
        {
            "lot_size": 1,
            "entry_price": 150,
            "exit_price": 151,
            "side": "Long",
            "quote_to_usd_rate": 1 / 150,
        },
        {
            **_stock_instrument(),
            "base_currency": "USD",
            "quote_currency": "JPY",
            "tick_size": 1,
            "pip_size": 1,
        },
    )

    assert result["native_pnl"] == pytest.approx(1)
    assert result["native_pnl_currency"] == "JPY"
    assert result["usd_pnl"] == pytest.approx(1 / 150)


@pytest.mark.parametrize(
    "overrides",
    [
        {"lot_size": 0.99},
        {"lot_size": 1.5},
        {"entry_price": 100.1},
    ],
)
def test_mapped_trade_rejects_invalid_lots_or_tick_prices(overrides):
    data = {
        "lot_size": 1,
        "entry_price": 100,
        "exit_price": 100.25,
        "side": "Long",
        "quote_to_usd_rate": 1,
    }
    data.update(overrides)

    with pytest.raises(ValidationError):
        TradeService._calculate_mapped_instrument_trade(
            data,
            _stock_instrument(),
        )


class _ConversionProvider:
    def __init__(self, candles_by_date):
        self.candles_by_date = candles_by_date
        self.calls = []

    def fetch_conversion_day(self, instrument, utc_date):
        self.calls.append((instrument, utc_date))
        return {
            "candles": self.candles_by_date.get((instrument, utc_date), [])
        }


def _usd_jpy_mapping() -> dict:
    return {
        "USD-JPY": {
            "base_currency": "USD",
            "quote_currency": "JPY",
            "quote_currency_unit_scale": 1,
            "catalog_group": "FX_MAJORS",
        }
    }


def test_conversion_uses_inverse_rate_from_last_completed_candle():
    event_time = datetime(2026, 9, 23, 10, 2, 30, tzinfo=timezone.utc)
    event_ms = int(event_time.timestamp() * 1000)
    provider = _ConversionProvider({
        ("USD-JPY", event_time.date()): [
            {"time_ms": event_ms - 90_000, "close": 150},
            # This candle closes after event_time and must not be used.
            {"time_ms": event_ms - 30_000, "close": 200},
        ]
    })

    result = ManualTradeConversionRateService(provider).quote_to_usd_rate(
        quote_currency="JPY",
        event_time=event_time,
        instruments=_usd_jpy_mapping(),
    )

    assert result["available"] is True
    assert result["quote_to_usd_rate"] == pytest.approx(1 / 150)
    assert result["rate_time"] == datetime.fromtimestamp(
        (event_ms - 30_000) / 1000, timezone.utc
    ).isoformat()
    assert result["route"][0]["direction"] == "inverse"


def test_conversion_searches_prior_utc_day_for_weekend_exit():
    event_time = datetime(2026, 10, 5, 0, 1, 30, tzinfo=timezone.utc)
    event_ms = int(event_time.timestamp() * 1000)
    friday = datetime(2026, 10, 2, tzinfo=timezone.utc).date()
    friday_close_open_ms = int(
        datetime(2026, 10, 2, 23, 58, tzinfo=timezone.utc).timestamp() * 1000
    )
    provider = _ConversionProvider({
        ("USD-JPY", friday): [
            {"time_ms": friday_close_open_ms, "close": 150},
        ]
    })

    result = ManualTradeConversionRateService(provider).quote_to_usd_rate(
        quote_currency="JPY",
        event_time=event_time,
        instruments=_usd_jpy_mapping(),
    )

    assert result["available"] is True
    assert result["quote_to_usd_rate"] == pytest.approx(1 / 150)
    assert provider.calls[-1] == ("USD-JPY", friday)


def test_conversion_uses_direct_pair_rate():
    event_time = datetime(2026, 9, 23, 10, 2, 30, tzinfo=timezone.utc)
    event_ms = int(event_time.timestamp() * 1000)
    provider = _ConversionProvider({
        ("GBP-USD", event_time.date()): [
            {"time_ms": event_ms - 90_000, "close": 1.25},
        ]
    })

    result = ManualTradeConversionRateService(provider).quote_to_usd_rate(
        quote_currency="GBP",
        event_time=event_time,
        instruments={
            "GBP-USD": {
                "base_currency": "GBP",
                "quote_currency": "USD",
                "catalog_group": "FX_MAJORS",
            }
        },
    )

    assert result["available"] is True
    assert result["quote_to_usd_rate"] == pytest.approx(1.25)
    assert result["route"][0]["direction"] == "direct"


def test_conversion_uses_shortest_two_pair_route():
    event_time = datetime(2026, 9, 23, 10, 2, 30, tzinfo=timezone.utc)
    event_ms = int(event_time.timestamp() * 1000)
    provider = _ConversionProvider({
        ("EUR-CHF", event_time.date()): [
            {"time_ms": event_ms - 90_000, "close": 0.95},
        ],
        ("EUR-USD", event_time.date()): [
            {"time_ms": event_ms - 90_000, "close": 1.1},
        ],
    })

    result = ManualTradeConversionRateService(provider).quote_to_usd_rate(
        quote_currency="CHF",
        event_time=event_time,
        instruments={
            "EUR-CHF": {
                "base_currency": "EUR",
                "quote_currency": "CHF",
                "catalog_group": "FX_CROSSES",
            },
            "EUR-USD": {
                "base_currency": "EUR",
                "quote_currency": "USD",
                "catalog_group": "FX_MAJORS",
            },
        },
    )

    assert result["available"] is True
    assert result["quote_to_usd_rate"] == pytest.approx(1.1 / 0.95)
    assert [leg["direction"] for leg in result["route"]] == [
        "inverse",
        "direct",
    ]
    assert len(provider.calls) == 2


def test_minor_unit_quote_uses_default_currency_scale():
    event_time = datetime(2026, 9, 23, 10, 2, 30, tzinfo=timezone.utc)

    result = ManualTradeConversionRateService().quote_to_usd_rate(
        quote_currency="USX",
        event_time=event_time,
        instruments={},
    )

    assert result["available"] is True
    assert result["quote_to_usd_rate"] == pytest.approx(0.01)
    assert result["quote_currency_unit_scale"] == pytest.approx(0.01)


def test_supplied_rate_is_marked_historical_only_when_it_matches_lookup():
    class RateService:
        def quote_to_usd_rate(self, **kwargs):
            return {
                "available": True,
                "quote_to_usd_rate": 0.0067,
                "quote_currency_unit_scale": 1,
                "rate_time": "2026-09-23T10:02:00+00:00",
                "route": [{"instrument": "USD-JPY", "direction": "inverse"}],
            }

    service = TradeService.__new__(TradeService)
    service.conversion_rate_service = RateService()
    instrument = {"quote_currency": "JPY"}
    mappings = {"instruments": {"USD-JPY": {}}}
    event_time = datetime(2026, 9, 23, 10, 2, 30, tzinfo=timezone.utc)

    historical = service._with_resolved_quote_rate(
        event_time,
        {"quote_to_usd_rate": 0.0067},
        instrument,
        mappings,
    )
    override = service._with_resolved_quote_rate(
        event_time,
        {"quote_to_usd_rate": 0.0068},
        instrument,
        mappings,
    )

    assert historical["conversion_rate_source"] == "historical"
    assert historical["conversion_rate_time"] == "2026-09-23T10:02:00+00:00"
    assert historical["conversion_route"][0]["instrument"] == "USD-JPY"
    assert override["conversion_rate_source"] == "manual"
    assert override["conversion_route"] == []
