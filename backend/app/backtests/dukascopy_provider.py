"""Adapter from the configured Dukascopy downloader to replay candles."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone


def download_combined_candles(*args, **kwargs):
    """Load the dependency API lazily for the backtest provider."""
    try:
        from dukascopy_market_data import download_combined_candles as download
    except ImportError as exc:
        raise RuntimeError(
            "The configured Dukascopy downloader is not installed."
        ) from exc
    return download(*args, **kwargs)


class DukascopyProvider:
    """Fetch in-memory COMB candles and derive component-wise midpoint OHLC."""

    source_side = "COMB"
    price_mode = "combined_midpoint"
    volume_semantics = "two_sided_quote_liquidity"

    def fetch_day(self, instrument: str, utc_date: date) -> dict:
        """Load one UTC date and return its real, available midpoint bars."""
        combined = download_combined_candles(instrument, utc_date, 1)
        candles = self._normalize_candles(combined, utc_date)

        candles.sort(key=lambda candle: candle["time_ms"])
        deduplicated = []
        seen_times = set()
        for candle in candles:
            if candle["time_ms"] in seen_times:
                continue
            seen_times.add(candle["time_ms"])
            deduplicated.append(candle)
        return {
            "utc_date": utc_date,
            "outcome": "data" if deduplicated else "empty",
            "candles": deduplicated,
        }

    def fetch_conversion_day(self, instrument: str, utc_date: date) -> dict:
        """Fetch COMB one-minute data for a quote-to-USD conversion pair.

        Conversion sources use the same midpoint and UTC-date contract as the
        instrument series. Direction (direct or inverse) is metadata carried
        by the preparation job and is applied only when resolving an event rate.
        """
        return self.fetch_day(instrument, utc_date)

    @staticmethod
    def _normalize_candles(combined, utc_date: date) -> list[dict]:
        output = []
        for candle in combined:
            time_ms = int(candle.timestamp_ms)
            candle_date = datetime.fromtimestamp(
                time_ms / 1000, tz=timezone.utc
            ).date()
            if candle_date != utc_date:
                continue

            open_price = DukascopyProvider._midpoint(
                candle.bid_open, candle.ask_open
            )
            high_price = DukascopyProvider._midpoint(
                candle.bid_high, candle.ask_high
            )
            low_price = DukascopyProvider._midpoint(
                candle.bid_low, candle.ask_low
            )
            close_price = DukascopyProvider._midpoint(
                candle.bid_close, candle.ask_close
            )
            volume = DukascopyProvider._number(
                candle.bid_volume, "bidVolume"
            ) + DukascopyProvider._number(candle.ask_volume, "askVolume")
            output.append(
                {
                    "time_ms": time_ms,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    # COMB side volumes are quoted liquidity, not executed
                    # trade volume. See metadata persisted with the snapshot.
                    "volume": volume,
                }
            )
        return output

    @staticmethod
    def _midpoint(bid, ask) -> float:
        bid_number = DukascopyProvider._number(bid, "bid price")
        ask_number = DukascopyProvider._number(ask, "ask price")
        # Independent side aggregation means the high and low values are
        # component-wise midpoint estimates, not synchronized tick extrema.
        return round((bid_number + ask_number) / 2, 12)

    @staticmethod
    def _number(value, field_name: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"Combined Dukascopy {field_name} must be finite.")
        return number
