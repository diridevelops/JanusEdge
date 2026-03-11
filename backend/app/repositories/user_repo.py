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

    def update_display_timezone(
        self, user_id: str, display_timezone: str
    ) -> bool:
        """
        Update a user's display timezone.

        Parameters:
            user_id: The user's ObjectId string.
            display_timezone: New display timezone.

        Returns:
            True if updated successfully.
        """
        from app.utils.datetime_utils import utc_now

        return self.update_one(
            user_id,
            {
                "$set": {
                    "display_timezone": display_timezone,
                    "updated_at": utc_now(),
                }
            },
        )

    def update_starting_equity(
        self, user_id: str, starting_equity: float
    ) -> bool:
        """
        Update a user's starting equity for simulations.

        Parameters:
            user_id: The user's ObjectId string.
            starting_equity: New starting equity value.

        Returns:
            True if updated successfully.
        """
        from app.utils.datetime_utils import utc_now

        return self.update_one(
            user_id,
            {
                "$set": {
                    "starting_equity": starting_equity,
                    "updated_at": utc_now(),
                }
            },
        )

    def update_symbol_mappings(
        self,
        user_id: str,
        symbol_mappings: dict,
    ) -> bool:
        """
        Update a user's symbol mappings.

        Parameters:
            user_id: The user's ObjectId string.
            symbol_mappings: New symbol mapping settings.

        Returns:
            True if updated successfully.
        """
        from app.utils.datetime_utils import utc_now

        return self.update_one(
            user_id,
            {
                "$set": {
                    "symbol_mappings": symbol_mappings,
                    "updated_at": utc_now(),
                }
            },
        )

    def update_portable_settings(
        self,
        user_id: str,
        timezone: str,
        display_timezone: str,
        starting_equity: float,
        symbol_mappings: dict,
    ) -> bool:
        """Update all portable user settings in one write."""
        from app.utils.datetime_utils import utc_now

        return self.update_one(
            user_id,
            {
                "$set": {
                    "timezone": timezone,
                    "display_timezone": display_timezone,
                    "starting_equity": starting_equity,
                    "symbol_mappings": symbol_mappings,
                    "updated_at": utc_now(),
                }
            },
        )
