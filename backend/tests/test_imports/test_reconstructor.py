"""Tests for trade reconstruction engine."""

from app.imports.parsers.base import ParsedExecution
from app.imports.reconstructor import (
    get_point_value,
    reconstruct_trades,
)


def _make_exec(
    symbol="MES",
    raw_symbol="MES 03-26",
    side="Buy",
    quantity=1,
    price=5000.0,
    timestamp="2026-01-01T10:00:00+00:00",
    account="TEST",
):
    """Helper to create a ParsedExecution."""
    return ParsedExecution(
        symbol=symbol,
        raw_symbol=raw_symbol,
        side=side,
        quantity=quantity,
        price=price,
        timestamp=timestamp,
        account=account,
    )


class TestGetPointValue:
    """Tests for point value lookup."""

    def test_mes_point_value(self):
        assert get_point_value("MES") == 5.0

    def test_es_point_value(self):
        assert get_point_value("ES") == 50.0

    def test_mnq_point_value(self):
        assert get_point_value("MNQ") == 2.0

    def test_unknown_defaults_to_one(self):
        assert get_point_value("UNKNOWN") == 1.0


class TestReconstructTrades:
    """Tests for trade reconstruction."""

    def test_simple_long_trade(self):
        executions = [
            _make_exec(
                side="Buy", price=5000.0,
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                side="Sell", price=5010.0,
                timestamp="2026-01-01T10:05:00+00:00",
            ),
        ]
        trades = reconstruct_trades(executions)

        assert len(trades) == 1
        t = trades[0]
        assert t.side == "Long"
        assert t.total_quantity == 1
        assert t.avg_entry_price == 5000.0
        assert t.avg_exit_price == 5010.0
        # P&L: (5010-5000) * 1 * $5 = $50
        assert t.gross_pnl == 50.0
        assert t.execution_count == 2

    def test_simple_short_trade(self):
        executions = [
            _make_exec(
                side="Sell", price=5050.0,
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                side="Buy", price=5040.0,
                timestamp="2026-01-01T10:03:00+00:00",
            ),
        ]
        trades = reconstruct_trades(executions)

        assert len(trades) == 1
        t = trades[0]
        assert t.side == "Short"
        # P&L: (5050-5040) * 1 * $5 = $50
        assert t.gross_pnl == 50.0

    def test_losing_long_trade(self):
        executions = [
            _make_exec(
                side="Buy", price=5000.0,
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                side="Sell", price=4990.0,
                timestamp="2026-01-01T10:05:00+00:00",
            ),
        ]
        trades = reconstruct_trades(executions)

        assert len(trades) == 1
        # P&L: (4990-5000) * 1 * $5 = -$50
        assert trades[0].gross_pnl == -50.0

    def test_two_consecutive_trades(self):
        executions = [
            _make_exec(
                side="Buy", price=5000.0,
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                side="Sell", price=5010.0,
                timestamp="2026-01-01T10:05:00+00:00",
            ),
            _make_exec(
                side="Buy", price=5020.0,
                timestamp="2026-01-01T10:10:00+00:00",
            ),
            _make_exec(
                side="Sell", price=5015.0,
                timestamp="2026-01-01T10:15:00+00:00",
            ),
        ]
        trades = reconstruct_trades(executions)

        assert len(trades) == 2
        assert trades[0].gross_pnl == 50.0
        assert trades[1].gross_pnl == -25.0

    def test_scale_in_long(self):
        executions = [
            _make_exec(
                side="Buy", price=5000.0, quantity=1,
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                side="Buy", price=5010.0, quantity=1,
                timestamp="2026-01-01T10:01:00+00:00",
            ),
            _make_exec(
                side="Sell", price=5020.0, quantity=2,
                timestamp="2026-01-01T10:05:00+00:00",
            ),
        ]
        trades = reconstruct_trades(executions)

        assert len(trades) == 1
        t = trades[0]
        assert t.total_quantity == 2
        # Avg entry: (5000+5010)/2 = 5005
        assert t.avg_entry_price == 5005.0
        assert t.avg_exit_price == 5020.0
        # P&L: (5020-5005) * 2 * $5 = $150
        assert t.gross_pnl == 150.0
        assert t.execution_count == 3

    def test_holding_time_calculation(self):
        executions = [
            _make_exec(
                side="Buy", price=5000.0,
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                side="Sell", price=5010.0,
                timestamp="2026-01-01T10:05:00+00:00",
            ),
        ]
        trades = reconstruct_trades(executions)
        assert trades[0].holding_time_seconds == 300

    def test_separate_accounts(self):
        executions = [
            _make_exec(
                side="Buy", price=5000.0,
                account="A",
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                side="Sell", price=5010.0,
                account="A",
                timestamp="2026-01-01T10:05:00+00:00",
            ),
            _make_exec(
                side="Buy", price=6000.0,
                account="B",
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                side="Sell", price=6020.0,
                account="B",
                timestamp="2026-01-01T10:05:00+00:00",
            ),
        ]
        trades = reconstruct_trades(executions)
        assert len(trades) == 2

    def test_different_symbols_separate_trades(self):
        executions = [
            _make_exec(
                symbol="MES", side="Buy", price=5000.0,
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                symbol="MES", side="Sell", price=5010.0,
                timestamp="2026-01-01T10:05:00+00:00",
            ),
            _make_exec(
                symbol="MNQ", raw_symbol="MNQ 03-26",
                side="Buy", price=20000.0,
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            _make_exec(
                symbol="MNQ", raw_symbol="MNQ 03-26",
                side="Sell", price=20010.0,
                timestamp="2026-01-01T10:05:00+00:00",
            ),
        ]
        trades = reconstruct_trades(executions)
        assert len(trades) == 2

    def test_empty_executions(self):
        trades = reconstruct_trades([])
        assert len(trades) == 0

    def test_with_real_ninjatrader_data(self):
        """
        Test with NinjaTrader-like data:
        Buy 1 MES @ 6925.50, Sell 1 MES @ 6922.50.
        """
        executions = [
            _make_exec(
                symbol="MES",
                raw_symbol="MES 03-26",
                side="Buy",
                quantity=1,
                price=6925.50,
                timestamp="2026-04-02T14:05:21+00:00",
                account="FNFTCH",
            ),
            _make_exec(
                symbol="MES",
                raw_symbol="MES 03-26",
                side="Sell",
                quantity=1,
                price=6922.50,
                timestamp="2026-04-02T14:05:49+00:00",
                account="FNFTCH",
            ),
        ]
        trades = reconstruct_trades(executions)

        assert len(trades) == 1
        t = trades[0]
        assert t.side == "Long"
        # P&L: (6922.50-6925.50) * 1 * $5 = -$15
        assert t.gross_pnl == -15.0
        assert t.symbol == "MES"
        assert t.account == "FNFTCH"
