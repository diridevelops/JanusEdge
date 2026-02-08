"""User repository for database operations."""

from typing import Optional

from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """Repository for user collection operations."""

    collection_name = "users"

    def find_by_username(
        self, username: str
    ) -> Optional[dict]:
        """
        Find a user by username.

        Parameters:
            username: The username to search for.

        Returns:
            User document or None.
        """
        return self.find_one({"username": username})

    def update_password(
        self, user_id: str, password_hash: str
    ) -> bool:
        """
        Update a user's password hash.

        Parameters:
            user_id: The user's ObjectId string.
            password_hash: New bcrypt hash.

        Returns:
            True if updated successfully.
        """
        from app.utils.datetime_utils import utc_now

        return self.update_one(
            user_id,
            {
                "$set": {
                    "password_hash": password_hash,
                    "updated_at": utc_now(),
                }
            },
        )

    def update_timezone(
        self, user_id: str, timezone: str
    ) -> bool:
        """
        Update a user's trading timezone.

        Parameters:
            user_id: The user's ObjectId string.
            timezone: New timezone string.

        Returns:
            True if updated successfully.
        """
        from app.utils.datetime_utils import utc_now

        return self.update_one(
            user_id,
            {
                "$set": {
                    "timezone": timezone,
                    "updated_at": utc_now(),
                }
            },
        )
