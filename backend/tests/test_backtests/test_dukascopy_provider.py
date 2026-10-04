"""In-memory COMB downloader adapter tests."""

from datetime import date
from decimal import Decimal

from dukascopy_market_data import CombinedAggregatedCandle


def _combined_candles():
    return (
        CombinedAggregatedCandle(
            timestamp_ms=1767571200000,
            bid_open=Decimal("1.1000"),
            bid_high=Decimal("1.1010"),
            bid_low=Decimal("1.0990"),
            bid_close=Decimal("1.1005"),
            ask_open=Decimal("1.1002"),
            ask_high=Decimal("1.1014"),
            ask_low=Decimal("1.0992"),
            ask_close=Decimal("1.1007"),
            bid_volume=10,
            ask_volume=20,
        ),
        CombinedAggregatedCandle(
            timestamp_ms=1767571320000,
            bid_open=Decimal("1.1020"),
            bid_high=Decimal("1.1030"),
            bid_low=Decimal("1.1010"),
            bid_close=Decimal("1.1025"),
            ask_open=Decimal("1.1022"),
            ask_high=Decimal("1.1034"),
            ask_low=Decimal("1.1012"),
            ask_close=Decimal("1.1027"),
            bid_volume=12,
            ask_volume=22,
        ),
    )


def test_fetch_day_requests_in_memory_comb_and_derives_midpoints(monkeypatch):
    import app.backtests.dukascopy_provider as provider_module

    calls = []

    def fake_download(*args, **kwargs):
        calls.append((args, kwargs))
        return _combined_candles()

    monkeypatch.setattr(
        provider_module, "download_combined_candles", fake_download
    )
    result = provider_module.DukascopyProvider().fetch_day(
        "EUR-USD", date(2026, 1, 5)
    )

    assert calls == [(("EUR-USD", date(2026, 1, 5), 1), {})]
    assert result["outcome"] == "data"
    assert result["utc_date"] == date(2026, 1, 5)
    assert result["candles"] == [
        {
            "time_ms": 1767571200000,
            "open": 1.1001,
            "high": 1.1012,
            "low": 1.0991,
            "close": 1.1006,
            "volume": 30,
        },
        {
            "time_ms": 1767571320000,
            "open": 1.1021,
            "high": 1.1032,
            "low": 1.1011,
            "close": 1.1026,
            "volume": 34,
        },
    ]


def test_fetch_day_preserves_empty_days(monkeypatch):
    import app.backtests.dukascopy_provider as provider_module

    monkeypatch.setattr(
        provider_module,
        "download_combined_candles",
        lambda *_args, **_kwargs: (),
    )
    result = provider_module.DukascopyProvider().fetch_day(
        "EUR-USD", date(2026, 1, 6)
    )

    assert result["outcome"] == "empty"
    assert result["candles"] == []


def test_fetch_day_discards_rows_outside_requested_utc_day(monkeypatch):
    import app.backtests.dukascopy_provider as provider_module

    next_day = CombinedAggregatedCandle(
        timestamp_ms=1767657600000,
        bid_open=Decimal("1.0"),
        bid_high=Decimal("1.0"),
        bid_low=Decimal("1.0"),
        bid_close=Decimal("1.0"),
        ask_open=Decimal("1.0"),
        ask_high=Decimal("1.0"),
        ask_low=Decimal("1.0"),
        ask_close=Decimal("1.0"),
        bid_volume=1,
        ask_volume=1,
    )
    monkeypatch.setattr(
        provider_module,
        "download_combined_candles",
        lambda *_args, **_kwargs: (_combined_candles()[0], next_day),
    )

    result = provider_module.DukascopyProvider().fetch_day(
        "EUR-USD", date(2026, 1, 5)
    )

    assert len(result["candles"]) == 1
    assert result["candles"][0]["time_ms"] == 1767571200000
