"""Auth refresh-session model helpers."""

from bson import ObjectId

from app.utils.datetime_utils import utc_now


def create_auth_refresh_session_doc(
    *,
    user_id: str,
    token_hash: str,
    user_agent: str | None = None,
) -> dict:
    """Create a refresh-session document for MongoDB insertion."""

    now = utc_now()
    return {
        "user_id": ObjectId(user_id),
        "token_hash": token_hash,
        "user_agent": user_agent or "",
        "created_at": now,
        "last_used_at": now,
        "updated_at": now,
        "revoked_at": None,
    }
