"""User model definition."""

from datetime import datetime
from typing import Optional

from app.utils.datetime_utils import utc_now


def create_user_doc(
    username: str,
    password_hash: str,
    timezone: str = "America/New_York",
) -> dict:
    """
    Create a user document for MongoDB insertion.

    Parameters:
        username: Unique username.
        password_hash: Bcrypt-hashed password.
        timezone: User's trading timezone.

    Returns:
        Dict ready for MongoDB insert.
    """
    now = utc_now()
    return {
        "username": username,
        "password_hash": password_hash,
        "timezone": timezone,
        "created_at": now,
        "updated_at": now,
    }
