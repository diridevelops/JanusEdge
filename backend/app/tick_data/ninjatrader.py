"""Helpers for parsing NinjaTrader tick-history text exports."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Iterator


@dataclass(frozen=True, slots=True)
class NinjaTraderTick:
    """One parsed NinjaTrader tick record normalized to UTC."""

    timestamp: datetime
    last_price: float
    bid_price: float
    ask_price: float
    size: int


def parse_ninjatrader_tick_line(line: str) -> NinjaTraderTick:
    """Parse one NinjaTrader tick line into a typed UTC tick."""

    raw_line = line.strip()
    if not raw_line:
        raise ValueError("Tick line is empty.")

    fields = raw_line.split(";")
    if len(fields) != 5:
        raise ValueError(
            "Tick line must contain timestamp, last, bid, ask, and size."
        )

    timestamp = _parse_timestamp(fields[0])
    last_price = _parse_float(fields[1], field_name="last price")
    bid_price = _parse_float(fields[2], field_name="bid price")
    ask_price = _parse_float(fields[3], field_name="ask price")
    size = _parse_size(fields[4])

    return NinjaTraderTick(
        timestamp=timestamp,
        last_price=last_price,
        bid_price=bid_price,
        ask_price=ask_price,
        size=size,
    )


def iter_ninjatrader_ticks(
    stream: Iterable[str],
) -> Iterator[NinjaTraderTick]:
    """Yield only valid parsed ticks from a text stream."""

    for line in stream:
        if not line.strip():
            continue

        try:
            yield parse_ninjatrader_tick_line(line)
        except ValueError:
            continue


def group_ticks_by_utc_date(
    ticks: Iterable[NinjaTraderTick],
) -> dict[date, list[NinjaTraderTick]]:
    """Group ticks by their UTC calendar day for daily storage."""

    grouped_ticks: defaultdict[date, list[NinjaTraderTick]] = (
        defaultdict(list)
    )
    for tick in ticks:
        utc_date = tick.timestamp.astimezone(timezone.utc).date()
        grouped_ticks[utc_date].append(tick)

    return dict(grouped_ticks)


def _parse_timestamp(raw_timestamp: str) -> datetime:
    """Parse the NinjaTrader timestamp fragment as a UTC datetime."""

    timestamp_parts = raw_timestamp.split()
    if len(timestamp_parts) != 3:
        raise ValueError(
            "Timestamp must contain date, time, and fractional seconds."
        )

    date_text, time_text, fractional_text = timestamp_parts

    try:
        base_timestamp = datetime.strptime(
            f"{date_text} {time_text}",
            "%Y%m%d %H%M%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("Timestamp has an invalid date or time value.") from exc

    microseconds, carry_seconds = _fractional_to_microseconds(
        fractional_text
    )
    return base_timestamp + timedelta(
        seconds=carry_seconds,
        microseconds=microseconds,
    )


def _fractional_to_microseconds(fractional_text: str) -> tuple[int, int]:
    """Convert up to seven fractional-second digits into microseconds."""

    if not fractional_text.isdigit() or len(fractional_text) > 7:
        raise ValueError("Fractional seconds must be 1 to 7 digits.")

    fractional_value = int(fractional_text.ljust(7, "0"))
    microseconds = (fractional_value + 5) // 10
    if microseconds == 1_000_000:
        return 0, 1
    return microseconds, 0


def _parse_float(raw_value: str, field_name: str) -> float:
    """Parse a numeric tick field as a float."""

    try:
        return float(raw_value.strip())
    except ValueError as exc:
        raise ValueError(
            f"{field_name.capitalize()} must be numeric."
        ) from exc


def _parse_size(raw_value: str) -> int:
    """Parse the tick size field and reject negative sizes."""

    try:
        size = int(raw_value.strip())
    except ValueError as exc:
        raise ValueError("Size must be an integer.") from exc

    if size < 0:
        raise ValueError("Size must be zero or greater.")
    return size