"""COMB downloader adapter tests with a local fake output file."""

from datetime import date
from types import SimpleNamespace

import pandas as pd


def _combined_frame():
    """Return combined source-side minute values, including one gap."""
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-05T00:00:00Z",
                    "2026-01-05T00:02:00Z",
                ],
                utc=True,
            ),
            "bidOpen": [1.1000, 1.1020],
            "bidHigh": [1.1010, 1.1030],
            "bidLow": [1.0990, 1.1010],
            "bidClose": [1.1005, 1.1025],
            "askOpen": [1.1002, 1.1022],
            "askHigh": [1.1014, 1.1034],
            "askLow": [1.0992, 1.1012],
            "askClose": [1.1007, 1.1027],
            "bidVolume": [10, 12],
            "askVolume": [20, 22],
        }
    )


def test_fetch_day_requests_comb_and_derives_component_midpoints(
    monkeypatch, tmp_path
):
    """COMB output is midpoint OHLC with summed quoted liquidity."""
    import app.backtests.dukascopy_provider as provider_module

    parquet_path = tmp_path / "combined.parquet"
    _combined_frame().to_parquet(parquet_path, index=False)
    calls = []

    def fake_downloads(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            output_paths=(parquet_path,),
            minute_count=2,
        )

    monkeypatch.setattr(
        provider_module, "run_downloads", fake_downloads
    )
    result = provider_module.DukascopyProvider().fetch_day(
        "EUR-USD", date(2026, 1, 5)
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:3] == ("EUR-USD", "COMB", date(2026, 1, 5))
    assert args[3] == 1
    assert kwargs["output_format"] == "parquet"

    assert result["outcome"] == "data"
    assert result["utc_date"] == date(2026, 1, 5)
    assert len(result["candles"]) == 2
    first, second = result["candles"]
    assert first == {
        "time_ms": 1767571200000,
        "open": 1.1001,
        "high": 1.1012,
        "low": 1.0991,
        "close": 1.1006,
        "volume": 30,
    }
    assert second["time_ms"] - first["time_ms"] == 120_000
    assert second["volume"] == 34


def test_fetch_day_returns_empty_outcome_without_synthesizing_rows(
    monkeypatch, tmp_path
):
    """A day with no source outputs stays empty, and missing minutes stay absent."""
    import app.backtests.dukascopy_provider as provider_module

    monkeypatch.setattr(
        provider_module,
        "run_downloads",
        lambda *args, **kwargs: SimpleNamespace(
            output_paths=(), minute_count=0
        ),
    )
    empty = provider_module.DukascopyProvider().fetch_day(
        "EUR-USD", date(2026, 1, 6)
    )

    assert empty["outcome"] == "empty"
    assert empty["candles"] == []

    parquet_path = tmp_path / "partial.parquet"
    _combined_frame().to_parquet(parquet_path, index=False)
    monkeypatch.setattr(
        provider_module,
        "run_downloads",
        lambda *args, **kwargs: SimpleNamespace(
            output_paths=(parquet_path,), minute_count=2
        ),
    )
    partial = provider_module.DukascopyProvider().fetch_day(
        "EUR-USD", date(2026, 1, 5)
    )

    assert len(partial["candles"]) == 2
    assert partial["candles"][1]["time_ms"] - partial["candles"][0]["time_ms"] == 120_000
