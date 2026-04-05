"""Repository for persistent auth refresh sessions."""

from bson import ObjectId

from app.repositories.base import BaseRepository


class AuthRefreshSessionRepository(BaseRepository):
    """Repository for auth_refresh_sessions collection."""

    collection_name = "auth_refresh_sessions"

    def find_active_by_token_hash(
        self,
        token_hash: str,
    ) -> dict | None:
        """Return one active refresh session by token hash."""

        return self.find_one(
            {
                "token_hash": token_hash,
                "revoked_at": None,
            }
        )

    def rotate_session(
        self,
        session_id: str,
        *,
        token_hash: str,
    ) -> bool:
        """Rotate a refresh session to a new token hash."""

        from app.utils.datetime_utils import utc_now

        now = utc_now()
        return self.update_one(
            session_id,
            {
                "$set": {
                    "token_hash": token_hash,
                    "last_used_at": now,
                    "updated_at": now,
                }
            },
        )

    def revoke_by_token_hash(
        self,
        token_hash: str,
    ) -> int:
        """Revoke the active session for the given token hash."""

        from app.utils.datetime_utils import utc_now

        now = utc_now()
        result = self.collection.update_many(
            {
                "token_hash": token_hash,
                "revoked_at": None,
            },
            {
                "$set": {
                    "revoked_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count

    def revoke_all_for_user(
        self,
        user_id: str,
    ) -> int:
        """Revoke all active refresh sessions for one user."""

        from app.utils.datetime_utils import utc_now

        now = utc_now()
        result = self.collection.update_many(
            {
                "user_id": ObjectId(user_id),
                "revoked_at": None,
            },
            {
                "$set": {
                    "revoked_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count
