"""Tests for NinjaTrader tick-data parsing helpers."""

from datetime import date, timezone
from io import StringIO

import pytest

from app.tick_data.ninjatrader import (
    group_ticks_by_utc_date,
    iter_ninjatrader_ticks,
    parse_ninjatrader_tick_line,
)


def test_parse_ninjatrader_tick_line_returns_tick() -> None:
    """A valid line is parsed into a UTC tick record."""

    tick = parse_ninjatrader_tick_line(
        "20260319 131858 6240000;6639.25;6639;6639.25;1"
    )

    assert tick.timestamp.isoformat() == "2026-03-19T13:18:58.624000+00:00"
    assert tick.timestamp.tzinfo == timezone.utc
    assert tick.last_price == 6639.25
    assert tick.bid_price == 6639.0
    assert tick.ask_price == 6639.25
    assert tick.size == 1


def test_parse_ninjatrader_tick_line_rejects_malformed_line() -> None:
    """Malformed lines fail fast with a parse error."""

    with pytest.raises(ValueError, match="must contain"):
        parse_ninjatrader_tick_line(
            "20260319 131858 6240000;6639.25;6639;6639.25"
        )


def test_parse_ninjatrader_tick_line_supports_fractional_seconds() -> None:
    """Seven-digit fractions are normalized to Python microseconds."""

    tick = parse_ninjatrader_tick_line(
        "20260319 131858 1234567;6639.25;6639;6639.25;1"
    )

    assert tick.timestamp.isoformat() == "2026-03-19T13:18:58.123457+00:00"


def test_iter_ninjatrader_ticks_skips_invalid_lines() -> None:
    """The stream iterator yields only valid ticks."""

    stream = StringIO(
        "\n"
        "20260319 131858 6240000;6639.25;6639;6639.25;1\n"
        "invalid line\n"
        "20260319 131859 0000000;6639.50;6639.25;6639.50;2\n"
    )

    ticks = list(iter_ninjatrader_ticks(stream))

    assert len(ticks) == 2
    assert [tick.size for tick in ticks] == [1, 2]


def test_group_ticks_by_utc_date_groups_multiple_days() -> None:
    """Ticks are grouped by UTC day boundaries for daily partitions."""

    ticks = [
        parse_ninjatrader_tick_line(
            "20260319 235959 9999990;6639.25;6639;6639.25;1"
        ),
        parse_ninjatrader_tick_line(
            "20260320 000000 0000000;6640.00;6639.75;6640.00;3"
        ),
        parse_ninjatrader_tick_line(
            "20260320 000001 1000000;6640.25;6640;6640.25;1"
        ),
    ]

    grouped_ticks = group_ticks_by_utc_date(ticks)

    assert list(grouped_ticks) == [
        date(2026, 3, 19),
        date(2026, 3, 20),
    ]
    assert len(grouped_ticks[date(2026, 3, 19)]) == 1
    assert len(grouped_ticks[date(2026, 3, 20)]) == 2