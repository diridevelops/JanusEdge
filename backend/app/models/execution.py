"""Execution model definition."""

from app.utils.datetime_utils import utc_now


def create_execution_doc(
    user_id,
    trade_account_id,
    import_batch_id,
    symbol: str,
    raw_symbol: str,
    side: str,
    quantity: int,
    price: float,
    timestamp,
    platform_execution_id: str = None,
    platform_order_id: str = None,
    order_type: str = None,
    entry_exit: str = None,
    commission: float = 0.0,
    raw_data: dict = None,
) -> dict:
    """
    Create an execution document for MongoDB insertion.

    Parameters:
        user_id: ObjectId of the user.
        trade_account_id: ObjectId of the trade account.
        import_batch_id: ObjectId of the import batch.
        symbol: Normalized symbol (e.g. 'MES').
        raw_symbol: Original symbol from CSV.
        side: 'Buy' or 'Sell'.
        quantity: Positive quantity.
        price: Execution price.
        timestamp: UTC datetime.
        platform_execution_id: ID from trading platform.
        platform_order_id: Order ID from platform.
        order_type: 'Market', 'Limit', 'Stop'.
        entry_exit: 'Entry' or 'Exit' if available.
        commission: Commission from CSV, if available.
        raw_data: Original row data for traceability.

    Returns:
        Dict ready for MongoDB insert.
    """
    doc = {
        "user_id": user_id,
        "trade_id": None,
        "import_batch_id": import_batch_id,
        "trade_account_id": trade_account_id,
        "symbol": symbol,
        "raw_symbol": raw_symbol,
        "side": side,
        "quantity": abs(quantity),
        "price": price,
        "timestamp": timestamp,
        "order_type": order_type,
        "entry_exit": entry_exit,
        "platform_execution_id": platform_execution_id,
        "platform_order_id": platform_order_id,
        "commission": commission,
        "raw_data": raw_data or {},
        "created_at": utc_now(),
    }
    return doc
