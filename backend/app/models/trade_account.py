"""Trade account model definition."""

from app.utils.datetime_utils import utc_now


def create_trade_account_doc(
    user_id,
    account_name: str,
    source_platform: str = "manual",
    display_name: str = None,
    starting_balance_usd: float | None = None,
    risk_percent: float | None = None,
) -> dict:
    """
    Create a trade account document.

    Parameters:
        user_id: ObjectId of the user.
        account_name: Original account from CSV.
        source_platform: 'ninjatrader', 'quantower', etc.
        display_name: Optional user-friendly name.
        starting_balance_usd: Initial balance for a simulated Backtest account.
        risk_percent: Immutable per-entry risk setting for a Backtest account.

    Returns:
        Dict ready for MongoDB insert.
    """
    now = utc_now()
    document = {
        "user_id": user_id,
        "account_name": account_name,
        "display_name": display_name or account_name,
        "notes": None,
        "status": "active",
        "source_platform": source_platform,
        "created_at": now,
        "updated_at": now,
    }
    if starting_balance_usd is not None:
        document["starting_balance_usd"] = starting_balance_usd
    if risk_percent is not None:
        document["risk_percent"] = risk_percent
    return document
