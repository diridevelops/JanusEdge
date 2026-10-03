"""Pure order-sizing and candle-execution rules for Backtest simulation."""

from decimal import Decimal

import pytest

from app.backtests.simulation_engine import (
    SimulationRuleError,
    allocate_opposing_fill_fifo,
    auto_size_lots,
    default_bracket_for_budget,
    entry_order_fill,
    normalize_market_reference_price,
    protective_exit_fill,
    projected_risk_usd,
    realized_native_pnl,
    validate_entry_bracket,
    validate_lots,
    validate_price,
)


EURUSD = {
    "instrument_type": "forex",
    "base_currency": "EUR",
    "quote_currency": "USD",
    "pip_size": 0.0001,
    "price_precision": 5,
    "contract_size": 100_000,
}


def test_entry_bracket_uses_correct_long_and_short_sides_and_allows_negative_prices():
    assert validate_entry_bracket(
        "buy", -1.0, -1.1, -0.9, EURUSD
    ) == (Decimal("-1.0"), Decimal("-1.1"), Decimal("-0.9"))
    assert validate_entry_bracket(
        "sell", 1.1, 1.2, 1.0, EURUSD
    ) == (Decimal("1.1"), Decimal("1.2"), Decimal("1.0"))

    with pytest.raises(SimulationRuleError, match="correct sides"):
        validate_entry_bracket("buy", 1.1, 1.2, 1.0, EURUSD)
    with pytest.raises(SimulationRuleError, match="decimal places"):
        validate_entry_bracket("buy", 1.100001, 1.09, 1.11, EURUSD)


@pytest.mark.parametrize("lots", [0, -0.001, 0.0009, 0.0011, float("nan"), float("inf"), True])
def test_lot_size_requires_finite_minimum_and_exact_increment(lots):
    with pytest.raises(SimulationRuleError):
        validate_lots(lots)


def test_price_validation_snaps_float_noise_but_rejects_extra_precision():
    with pytest.raises(SimulationRuleError, match="decimal places"):
        validate_price(1.200001, EURUSD, "entry_price")

    assert validate_price(1.2 + 0.001, EURUSD, "high") == Decimal("1.20100")


def test_frozen_instrument_tick_and_lot_rules_allow_instrument_specific_grids():
    cfd = {
        # Tick size is authoritative; a stale precision value from an older
        # saved settings row must not override the implied two decimals.
        "price_precision": 6,
        "tick_size": 0.25,
        "pip_size": 0.25,
        "contract_size": 1,
        "min_lots": 0.01,
        "lot_increment": 0.005,
    }
    assert validate_price(12.5, cfd, "entry_price") == Decimal("12.50")
    with pytest.raises(SimulationRuleError, match="tick size"):
        validate_price(12.6, cfd, "entry_price")
    assert validate_lots(0.01, cfd) == Decimal("0.01")
    assert validate_lots(0.015, cfd) == Decimal("0.015")
    with pytest.raises(SimulationRuleError, match="at least 0.01"):
        validate_lots(0.005, cfd)
    with pytest.raises(SimulationRuleError, match="0.005 increments"):
        validate_lots(0.012, cfd)


def test_default_bracket_uses_current_risk_budget_and_starts_at_one_r():
    bracket = default_bracket_for_budget(
        side="buy",
        entry_price=1.10000,
        risk_budget_usd=100,
        quote_to_usd_rate=1,
        metadata=EURUSD,
    )
    assert bracket == {"stop_loss": 1.099, "take_profit": 1.101}

    short = default_bracket_for_budget(
        side="sell",
        entry_price=1.1,
        risk_budget_usd=100,
        quote_to_usd_rate=1,
        metadata=EURUSD,
    )
    assert short == {"stop_loss": 1.101, "take_profit": 1.099}


def test_auto_size_rounds_down_accounts_for_costs_and_blocks_over_budget_minimum():
    costs = {
        "total_spread_pips": 1,
        "slippage_pips": 0.5,
        "commission_usd_per_lot_per_side": 3,
    }
    lots = auto_size_lots(
        risk_budget_usd=100,
        entry_price=1.1,
        stop_loss=1.099,
        quote_to_usd_rate=1,
        metadata=EURUSD,
        cost_profile=costs,
    )
    assert lots == Decimal("0.793")
    assert projected_risk_usd(
        lots=lots,
        entry_price=1.1,
        stop_loss=1.099,
        quote_to_usd_rate=1,
        metadata=EURUSD,
        cost_profile=costs,
    ) <= Decimal("100")

    with pytest.raises(SimulationRuleError, match="minimum 0.001"):
        auto_size_lots(
            risk_budget_usd=0.01,
            entry_price=1.1,
            stop_loss=1.09,
            quote_to_usd_rate=1,
            metadata=EURUSD,
            cost_profile=costs,
        )


def test_market_entry_waits_for_a_future_candle_and_uses_only_its_open():
    order = {
        "status": "pending",
        "order_type": "market",
        "side": "buy",
        "lots": 0.1,
        "eligible_source_index": 12,
    }
    candle = {"open": 1.1, "high": 2.0, "low": 0.5, "close": 1.8}
    assert entry_order_fill(
        order, candle, 11, metadata=EURUSD
    ) is None
    fill = entry_order_fill(order, candle, 12, metadata=EURUSD)
    assert fill["reference_price"] == 1.1
    assert fill["fill_price"] == 1.1


def test_market_entry_accepts_half_tick_midpoint_open_and_rounds_fill_adversely():
    order = {
        "status": "pending",
        "order_type": "market",
        "side": "buy",
        "lots": 0.1,
        "eligible_source_index": 1,
    }
    candle = {
        "open": 1.100005,
        "high": 1.100015,
        "low": 1.099995,
        "close": 1.100005,
    }

    buy_fill = entry_order_fill(order, candle, 1, metadata=EURUSD)
    assert buy_fill["reference_price"] == 1.10001
    assert buy_fill["fill_price"] == 1.10001

    order["side"] = "sell"
    sell_fill = entry_order_fill(order, candle, 1, metadata=EURUSD)
    assert sell_fill["reference_price"] == 1.1
    assert sell_fill["fill_price"] == 1.1
    assert normalize_market_reference_price(
        candle["close"], EURUSD, "entry_price"
    ) == Decimal("1.10001")


def test_limit_entry_requires_future_high_low_touch_and_keeps_exact_price():
    order = {
        "status": "pending",
        "order_type": "limit",
        "side": "buy",
        "entry_price": 1.1,
        "lots": 0.1,
        "eligible_source_index": 4,
    }
    gap_only = {"open": 1.099, "high": 1.0995, "low": 1.0985, "close": 1.0992}
    assert entry_order_fill(order, gap_only, 4, metadata=EURUSD) is None

    wick_touch = {
        "open": 1.099,
        "high": 1.100205,
        "low": 1.098505,
        "close": 1.0998,
    }
    fill = entry_order_fill(
        order,
        wick_touch,
        4,
        metadata=EURUSD,
        cost_profile={"total_spread_pips": 1, "slippage_pips": 1},
    )
    assert fill["reference_price"] == 1.1
    assert fill["fill_price"] == 1.1
    assert fill["spread_cost"] == pytest.approx(0.5)
    assert fill["slippage_cost"] == pytest.approx(1.0)


def test_oco_chooses_stop_when_stop_and_target_touch_in_the_same_candle():
    position = {
        "side": "long",
        "status": "open",
        "remaining_lots": 0.1,
        "stop_loss_price": 1.09,
        "take_profit_price": 1.11,
        "stop_loss_eligible_source_index": 8,
        "take_profit_eligible_source_index": 8,
    }
    both_touched = {"open": 1.1, "high": 1.12, "low": 1.08, "close": 1.1}
    assert protective_exit_fill(
        position, both_touched, 7, metadata=EURUSD
    ) is None
    fill = protective_exit_fill(position, both_touched, 8, metadata=EURUSD)
    assert fill["exit_role"] == "protective_stop"
    assert fill["reference_price"] == 1.09


def test_protective_stop_uses_adverse_gap_open_and_target_keeps_limit_price():
    position = {
        "side": "long",
        "status": "open",
        "remaining_lots": 0.1,
        "stop_loss_price": 1.09,
        "take_profit_price": 1.11,
    }
    gap = {"open": 1.08, "high": 1.09, "low": 1.07, "close": 1.085}
    stop_fill = protective_exit_fill(position, gap, 9, metadata=EURUSD)
    assert stop_fill["exit_role"] == "protective_stop"
    assert stop_fill["reference_price"] == 1.08

    target = {"open": 1.10, "high": 1.12, "low": 1.10, "close": 1.12}
    target_fill = protective_exit_fill(position, target, 9, metadata=EURUSD)
    assert target_fill["exit_role"] == "protective_target"
    assert target_fill["reference_price"] == 1.11
    assert target_fill["fill_price"] == 1.11


def test_protective_stop_accepts_half_tick_midpoint_ohlc():
    position = {
        "side": "long",
        "status": "open",
        "remaining_lots": 0.1,
        "stop_loss_price": 1.09,
        "take_profit_price": 1.11,
    }
    gap = {
        "open": 1.079995,
        "high": 1.080005,
        "low": 1.079985,
        "close": 1.080001,
    }

    fill = protective_exit_fill(position, gap, 9, metadata=EURUSD)
    assert fill["exit_role"] == "protective_stop"
    assert fill["reference_price"] == 1.07999
    assert fill["fill_price"] == 1.07999


def test_opposing_fill_allocation_is_fifo_and_returns_reverse_excess():
    positions = [
        {"position_id": "newer", "side": "short", "remaining_lots": 0.1, "opened_sequence": 2},
        {"position_id": "older", "side": "short", "remaining_lots": 0.2, "opened_sequence": 1},
        {"position_id": "same-side", "side": "long", "remaining_lots": 0.5, "opened_sequence": 0},
    ]
    allocations, excess = allocate_opposing_fill_fifo("buy", 0.35, positions)
    assert allocations == [
        {"position_id": "older", "lots": 0.2},
        {"position_id": "newer", "lots": 0.1},
    ]
    assert excess == Decimal("0.050")


def test_native_pnl_is_quote_currency_and_directional():
    assert realized_native_pnl(
        side="long",
        entry_price=1.1,
        exit_price=1.101,
        lots=0.1,
        metadata=EURUSD,
    ) == Decimal("10.00000")
    assert realized_native_pnl(
        side="short",
        entry_price=1.1,
        exit_price=1.101,
        lots=0.1,
        metadata=EURUSD,
    ) == Decimal("-10.00000")
