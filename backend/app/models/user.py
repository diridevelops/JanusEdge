"""User model definition."""

from datetime import datetime
from typing import Optional

from app.utils.datetime_utils import utc_now


def create_user_doc(
    username: str,
    password_hash: str,
    timezone: str = "America/New_York",
    display_timezone: str | None = None,
    starting_equity: float = 10000.0,
) -> dict:
    """
    Create a user document for MongoDB insertion.

    Parameters:
        username: Unique username.
        password_hash: Bcrypt-hashed password.
        timezone: User's trading timezone.
        display_timezone: Timezone for UI display
            (defaults to trading timezone).
        starting_equity: Initial account equity for
            Monte Carlo simulations (default 50 000).

    Returns:
        Dict ready for MongoDB insert.
    """
    now = utc_now()
    return {
        "username": username,
        "password_hash": password_hash,
        "timezone": timezone,
        "display_timezone": display_timezone or timezone,
        "starting_equity": starting_equity,
        "created_at": now,
        "updated_at": now,
    }
