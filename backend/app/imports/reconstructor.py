"""Trade reconstruction engine — groups executions into trades."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from app.imports.parsers.base import ParsedExecution


# Instrument point-value configuration
INSTRUMENT_SPECS = {
    "MES": {"point_value": 5.0, "tick_size": 0.25},
    "ES": {"point_value": 50.0, "tick_size": 0.25},
    "MNQ": {"point_value": 2.0, "tick_size": 0.25},
    "NQ": {"point_value": 20.0, "tick_size": 0.25},
    "MYM": {"point_value": 0.5, "tick_size": 1.0},
    "YM": {"point_value": 5.0, "tick_size": 1.0},
    "MCL": {"point_value": 100.0, "tick_size": 0.01},
    "CL": {"point_value": 1000.0, "tick_size": 0.01},
    "GC": {"point_value": 100.0, "tick_size": 0.1},
    "MGC": {"point_value": 10.0, "tick_size": 0.1},
}


@dataclass
class ReconstructedTrade:
    """A trade reconstructed from executions."""

    symbol: str
    raw_symbol: str
    side: str  # 'Long' or 'Short'
    total_quantity: int
    max_quantity: int
    avg_entry_price: float
    avg_exit_price: float
    gross_pnl: float
    entry_time: str  # ISO format
    exit_time: str  # ISO format
    holding_time_seconds: int
    execution_count: int
    executions: List[ParsedExecution]
    fee: float = 0.0
    account: str = ""


def get_point_value(symbol: str) -> float:
    """
    Get the point value for an instrument.

    Parameters:
        symbol: Normalized symbol (e.g., 'MES').

    Returns:
        Dollar value per point of price movement.
    """
    spec = INSTRUMENT_SPECS.get(symbol)
    if spec:
        return spec["point_value"]
    # Default to 1.0 for unknown instruments
    return 1.0


def reconstruct_trades(
    executions: List[ParsedExecution],
    method: str = "FIFO",
) -> List[ReconstructedTrade]:
    """
    Reconstruct flat-to-flat trades from executions.

    Groups executions by symbol + account, sorts by time,
    and creates trades using FIFO position accounting.

    Parameters:
        executions: List of parsed executions.
        method: Reconstruction method ('FIFO').

    Returns:
        List of reconstructed trades.
    """
    # Group by (symbol, account)
    groups = {}
    for ex in executions:
        key = (ex.symbol, ex.account)
        if key not in groups:
            groups[key] = []
        groups[key].append(ex)

    trades = []
    for (symbol, account), group_execs in groups.items():
        # Sort by timestamp
        group_execs.sort(key=lambda e: e.timestamp)
        group_trades = _reconstruct_fifo(
            symbol, account, group_execs
        )
        trades.extend(group_trades)

    # Sort all trades by entry time
    trades.sort(key=lambda t: t.entry_time)
    return trades


def _reconstruct_fifo(
    symbol: str,
    account: str,
    executions: List[ParsedExecution],
) -> List[ReconstructedTrade]:
    """
    FIFO reconstruction for a single symbol+account.

    Walks through executions tracking net position.
    When position goes flat (0), a trade is completed.

    Parameters:
        symbol: Normalized symbol.
        account: Account name.
        executions: Sorted executions for this group.

    Returns:
        List of reconstructed trades.
    """
    trades = []
    current_position = 0
    current_trade_execs = []

    # Tracking for entries
    entry_prices = []  # (qty, price)
    entry_qty_total = 0

    for ex in executions:
        signed_qty = ex.quantity
        if ex.side == "Sell":
            signed_qty = -signed_qty

        prev_position = current_position
        current_position += signed_qty
        current_trade_execs.append(ex)

        # Track entry fills
        if prev_position == 0:
            # Start of new position
            entry_prices = [(ex.quantity, ex.price)]
            entry_qty_total = ex.quantity
        elif (
            (prev_position > 0 and signed_qty > 0)
            or (prev_position < 0 and signed_qty < 0)
        ):
            # Scale-in (same direction)
            entry_prices.append(
                (ex.quantity, ex.price)
            )
            entry_qty_total += ex.quantity

        # Check if position is flat
        if current_position == 0 and current_trade_execs:
            trade = _build_trade(
                symbol, account, current_trade_execs,
                entry_prices, entry_qty_total,
            )
            trades.append(trade)

            current_trade_execs = []
            entry_prices = []
            entry_qty_total = 0

        # Handle position reversal
        elif (
            prev_position != 0
            and current_position != 0
            and (
                (prev_position > 0
                 and current_position < 0)
                or (prev_position < 0
                    and current_position > 0)
            )
        ):
            # Split: close old position, open new
            # For now, handle as a single trade closure
            trade = _build_trade(
                symbol, account, current_trade_execs,
                entry_prices, entry_qty_total,
            )
            trades.append(trade)

            # Start new position with remaining qty
            remainder_qty = abs(current_position)
            current_trade_execs = [ex]
            entry_prices = [(remainder_qty, ex.price)]
            entry_qty_total = remainder_qty

    # Handle open position at end (if any)
    if current_trade_execs and current_position != 0:
        trade = _build_trade(
            symbol, account, current_trade_execs,
            entry_prices, entry_qty_total,
            is_open=True,
        )
        trades.append(trade)

    return trades


def _build_trade(
    symbol: str,
    account: str,
    executions: List[ParsedExecution],
    entry_prices: list,
    entry_qty_total: int,
    is_open: bool = False,
) -> ReconstructedTrade:
    """
    Build a ReconstructedTrade from its executions.

    Parameters:
        symbol: Normalized symbol.
        account: Account name.
        executions: All executions in this trade.
        entry_prices: List of (qty, price) for entries.
        entry_qty_total: Total entry quantity.
        is_open: Whether trade is still open.

    Returns:
        ReconstructedTrade instance.
    """
    first_exec = executions[0]
    last_exec = executions[-1]

    # Determine side from first execution
    side = "Long" if first_exec.side == "Buy" else "Short"

    # Calculate average entry price
    if entry_qty_total > 0:
        avg_entry = sum(
            qty * price
            for qty, price in entry_prices
        ) / entry_qty_total
    else:
        avg_entry = first_exec.price

    # Calculate average exit price
    exit_execs = [
        e for e in executions
        if (
            (side == "Long" and e.side == "Sell")
            or (side == "Short" and e.side == "Buy")
        )
    ]
    exit_qty_total = sum(e.quantity for e in exit_execs)
    if exit_qty_total > 0:
        avg_exit = sum(
            e.quantity * e.price for e in exit_execs
        ) / exit_qty_total
    else:
        avg_exit = last_exec.price

    # Calculate gross P&L
    point_value = get_point_value(symbol)
    total_qty = entry_qty_total

    if side == "Long":
        gross_pnl = (
            (avg_exit - avg_entry)
            * total_qty * point_value
        )
    else:
        gross_pnl = (
            (avg_entry - avg_exit)
            * total_qty * point_value
        )

    if is_open:
        gross_pnl = 0.0

    # Calculate max position
    max_qty = 0
    running = 0
    for ex in executions:
        if (
            (side == "Long" and ex.side == "Buy")
            or (side == "Short" and ex.side == "Sell")
        ):
            running += ex.quantity
        else:
            running -= ex.quantity
        max_qty = max(max_qty, abs(running))

    # Calculate holding time
    entry_time = first_exec.timestamp
    exit_time = last_exec.timestamp
    try:
        entry_dt = datetime.fromisoformat(entry_time)
        exit_dt = datetime.fromisoformat(exit_time)
        holding_seconds = int(
            (exit_dt - entry_dt).total_seconds()
        )
    except Exception:
        holding_seconds = 0

    total_commission = round(
        sum(ex.commission for ex in executions), 2
    )

    return ReconstructedTrade(
        symbol=first_exec.symbol,
        raw_symbol=first_exec.raw_symbol,
        side=side,
        total_quantity=total_qty,
        max_quantity=max(max_qty, total_qty),
        avg_entry_price=round(avg_entry, 6),
        avg_exit_price=round(avg_exit, 6),
        gross_pnl=round(gross_pnl, 2),
        entry_time=entry_time,
        exit_time=exit_time,
        holding_time_seconds=holding_seconds,
        execution_count=len(executions),
        executions=executions,
        fee=total_commission,
        account=account,
    )
