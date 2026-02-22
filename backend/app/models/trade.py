"""Trade model definition."""

from app.utils.datetime_utils import utc_now


def create_trade_doc(
    user_id,
    trade_account_id,
    import_batch_id,
    symbol: str,
    raw_symbol: str,
    side: str,
    total_quantity: int,
    max_quantity: int,
    avg_entry_price: float,
    avg_exit_price: float,
    gross_pnl: float,
    fee: float,
    fee_source: str,
    net_pnl: float,
    initial_risk: float,
    entry_time,
    exit_time,
    holding_time_seconds: int,
    execution_count: int,
    source: str = "imported",
    status: str = "closed",
) -> dict:
    """
    Create a trade document for MongoDB insertion.

    Parameters:
        user_id: ObjectId of the user.
        trade_account_id: ObjectId of the trade account.
        import_batch_id: ObjectId of the import batch.
        symbol: Normalized symbol.
        raw_symbol: Original symbol from CSV.
        side: 'Long' or 'Short'.
        total_quantity: Total contracts traded.
        max_quantity: Peak position size.
        avg_entry_price: Weighted average entry.
        avg_exit_price: Weighted average exit.
        gross_pnl: Profit/loss before fees.
        fee: Total fee for this trade.
        fee_source: 'csv', 'import_entry', 'manual_edit'.
        net_pnl: Profit/loss after fees.
        initial_risk: User-defined initial risk in currency.
        entry_time: UTC datetime of first entry.
        exit_time: UTC datetime of last exit.
        holding_time_seconds: Duration in seconds.
        execution_count: Number of fills.
        source: 'imported' or 'manual'.
        status: 'open', 'closed', or 'deleted'.

    Returns:
        Dict ready for MongoDB insert.
    """
    now = utc_now()
    return {
        "user_id": user_id,
        "trade_account_id": trade_account_id,
        "import_batch_id": import_batch_id,
        "symbol": symbol,
        "raw_symbol": raw_symbol,
        "side": side,
        "total_quantity": total_quantity,
        "max_quantity": max_quantity,
        "avg_entry_price": avg_entry_price,
        "avg_exit_price": avg_exit_price,
        "gross_pnl": gross_pnl,
        "fee": fee,
        "fee_source": fee_source,
        "fee_last_edited": None,
        "net_pnl": net_pnl,
        "initial_risk": initial_risk,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "holding_time_seconds": holding_time_seconds,
        "execution_count": execution_count,
        "source": source,
        "manually_adjusted": False,
        "status": status,
        "tag_ids": [],
        "strategy": None,
        "pre_trade_notes": None,
        "post_trade_notes": None,
        "attachments": [],
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
