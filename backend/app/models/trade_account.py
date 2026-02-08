"""Trade account model definition."""

from app.utils.datetime_utils import utc_now


def create_trade_account_doc(
    user_id,
    account_name: str,
    source_platform: str = "manual",
    display_name: str = None,
) -> dict:
    """
    Create a trade account document.

    Parameters:
        user_id: ObjectId of the user.
        account_name: Original account from CSV.
        source_platform: 'ninjatrader', 'quantower', etc.
        display_name: Optional user-friendly name.

    Returns:
        Dict ready for MongoDB insert.
    """
    now = utc_now()
    return {
        "user_id": user_id,
        "account_name": account_name,
        "display_name": display_name or account_name,
        "notes": None,
        "status": "active",
        "source_platform": source_platform,
        "created_at": now,
        "updated_at": now,
    }
