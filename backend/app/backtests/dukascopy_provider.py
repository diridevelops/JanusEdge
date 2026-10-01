"""Adapter from the pinned Dukascopy downloader to replay candles."""

from __future__ import annotations

import math
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd


def run_downloads(*args, **kwargs):
    """Load the downloader lazily so unrelated API surfaces can start."""
    try:
        from dukascopy_market_data import run_downloads as download
    except ImportError as exc:
        raise RuntimeError(
            "The pinned Dukascopy downloader is not installed."
        ) from exc
    return download(*args, **kwargs)


class DukascopyProvider:
    """Fetch one COMB minute file and derive component-wise midpoint OHLC."""

    source_side = "COMB"
    price_mode = "combined_midpoint"
    volume_semantics = "two_sided_quote_liquidity"

    def fetch_day(self, instrument: str, utc_date: date) -> dict:
        """Download one UTC date and return its real, available minute bars."""
        with tempfile.TemporaryDirectory(prefix="janusedge-backtest-") as temp:
            result = run_downloads(
                instrument,
                self.source_side,
                utc_date,
                1,
                output_root=Path(temp),
                output_format="parquet",
            )
            candles = []
            for output_path in result.output_paths:
                frame = pd.read_parquet(output_path)
                candles.extend(self._normalize_frame(frame, utc_date))

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
    def _normalize_frame(frame: pd.DataFrame, utc_date: date) -> list[dict]:
        required_columns = {
            "timestamp",
            "bidOpen",
            "bidHigh",
            "bidLow",
            "bidClose",
            "askOpen",
            "askHigh",
            "askLow",
            "askClose",
            "bidVolume",
            "askVolume",
        }
        missing = required_columns - set(frame.columns)
        if missing:
            raise ValueError(
                "Combined Dukascopy output is missing columns: "
                + ", ".join(sorted(missing))
            )

        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        output = []
        for index, timestamp in enumerate(timestamps):
            time_ms = int(timestamp.value // 1_000_000)
            if timestamp.date() != utc_date:
                continue

            values = frame.iloc[index]
            open_price = DukascopyProvider._midpoint(
                values["bidOpen"], values["askOpen"]
            )
            high_price = DukascopyProvider._midpoint(
                values["bidHigh"], values["askHigh"]
            )
            low_price = DukascopyProvider._midpoint(
                values["bidLow"], values["askLow"]
            )
            close_price = DukascopyProvider._midpoint(
                values["bidClose"], values["askClose"]
            )
            volume = DukascopyProvider._number(
                values["bidVolume"], "bidVolume"
            ) + DukascopyProvider._number(values["askVolume"], "askVolume")
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
