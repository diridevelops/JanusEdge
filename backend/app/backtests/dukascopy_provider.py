"""Adapter from the pinned Dukascopy downloader to replay candles."""

from __future__ import annotations

import math
import logging
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd


_UPSTREAM_REQUEST_INTERVAL_SECONDS = 1.0
_UPSTREAM_RATE_LIMIT_BACKOFF_FACTOR = 5.0
_UPSTREAM_RATE_LIMIT_RECOVERY_SECONDS = (30.0, 60.0)
_upstream_request_lock = threading.Lock()
_next_upstream_request_at = 0.0
_logger = logging.getLogger(__name__)


def _wait_for_upstream_request_slot() -> None:
    """Serialize this process's requests to the public Dukascopy endpoint."""
    global _next_upstream_request_at
    with _upstream_request_lock:
        now = time.monotonic()
        delay = max(0.0, _next_upstream_request_at - now)
        if delay:
            time.sleep(delay)
        _next_upstream_request_at = (
            time.monotonic() + _UPSTREAM_REQUEST_INTERVAL_SECONDS
        )


def _retry_after_seconds(value: str | None) -> float:
    """Parse the standard seconds or HTTP-date forms of Retry-After."""
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


def _retry_after_from_error(error: BaseException) -> float | None:
    """Find an upstream 429 in the downloader's chained exception."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, urllib.error.HTTPError) and current.code == 429:
            return _retry_after_seconds(current.headers.get("Retry-After"))
        current = current.__cause__ or current.__context__
    return None


def _download_json_with_rate_limit_backoff(url: str) -> bytes:
    """Use the pinned downloader's retry contract with slower 429 recovery."""
    try:
        from dukascopy_market_data.candles import download_json_bytes
    except ImportError as exc:
        raise RuntimeError(
            "The pinned Dukascopy downloader is not installed."
        ) from exc

    response_state: dict[str, float | int] = {}

    def opener(request, *, timeout):
        _wait_for_upstream_request_slot()
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response_state["status"] = exc.code
            response_state["retry_after"] = _retry_after_seconds(
                exc.headers.get("Retry-After")
            )
            raise

    def sleep_before_retry(delay: float) -> None:
        if response_state.get("status") == 429:
            delay = max(
                delay * _UPSTREAM_RATE_LIMIT_BACKOFF_FACTOR,
                float(response_state.get("retry_after", 0.0)),
            )
        time.sleep(delay)
        response_state.clear()

    for attempt in range(len(_UPSTREAM_RATE_LIMIT_RECOVERY_SECONDS) + 1):
        try:
            return download_json_bytes(
                url,
                opener=opener,
                sleeper=sleep_before_retry,
            )
        except Exception as exc:
            retry_after = _retry_after_from_error(exc)
            if (
                retry_after is None
                or attempt >= len(_UPSTREAM_RATE_LIMIT_RECOVERY_SECONDS)
            ):
                raise
            delay = max(
                _UPSTREAM_RATE_LIMIT_RECOVERY_SECONDS[attempt], retry_after
            )
            _logger.warning(
                "Dukascopy rate-limited %s; retrying after %.0f seconds.",
                url,
                delay,
            )
            time.sleep(delay)
    raise AssertionError("Unreachable after exhausted Dukascopy retries.")


def run_downloads(*args, **kwargs):
    """Load the downloader lazily so unrelated API surfaces can start."""
    try:
        from dukascopy_market_data import run_downloads as download
    except ImportError as exc:
        raise RuntimeError(
            "The pinned Dukascopy downloader is not installed."
        ) from exc
    kwargs.setdefault("fetcher", _download_json_with_rate_limit_backoff)
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
