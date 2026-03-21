"""Helpers for building candle datasets from raw ticks."""

from __future__ import annotations

import pandas as pd


SUPPORTED_CANDLE_TIMEFRAMES = (
    "1m",
    "5m",
    "15m",
    "1h",
)

_TIMEFRAME_TO_FREQUENCY = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "1d": "1d",
}


def build_candles_from_ticks(
    ticks_frame: pd.DataFrame,
    timeframe: str,
) -> pd.DataFrame:
    """Aggregate raw ticks into candle bars for the requested timeframe."""

    if timeframe not in _TIMEFRAME_TO_FREQUENCY:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    if ticks_frame.empty:
        return pd.DataFrame(
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    frame = ticks_frame.copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
    )
    frame = frame.sort_values("timestamp")

    aggregated = (
        frame.resample(
            _TIMEFRAME_TO_FREQUENCY[timeframe],
            on="timestamp",
            label="left",
            closed="left",
        )
        .agg(
            open=("last_price", "first"),
            high=("last_price", "max"),
            low=("last_price", "min"),
            close=("last_price", "last"),
            volume=("size", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )

    aggregated["time"] = (
        aggregated["timestamp"].astype("int64") // 10**9
    ).astype(int)
    aggregated = aggregated.drop(columns=["timestamp"])
    aggregated["volume"] = aggregated["volume"].astype(int)
    return aggregated[
        ["time", "open", "high", "low", "close", "volume"]
    ]