"""Trade account repository for database operations."""

from typing import List, Optional

from bson import ObjectId

from app.repositories.base import BaseRepository
from app.utils.datetime_utils import utc_now


class AccountRepository(BaseRepository):
    """Repository for trade_accounts collection."""

    collection_name = "trade_accounts"

    def find_by_user(
        self, user_id: str, status: str = None
    ) -> List[dict]:
        """
        Find all trade accounts for a user.

        Parameters:
            user_id: User's ObjectId string.
            status: Optional filter by status.

        Returns:
            List of trade account documents.
        """
        query = {"user_id": ObjectId(user_id)}
        if status:
            query["status"] = status
        return self.find_many(
            query, sort=[("created_at", -1)]
        )

    def find_or_create(
        self,
        user_id: str,
        account_name: str,
        source_platform: str,
    ) -> dict:
        """
        Find existing account or create a new one.

        Parameters:
            user_id: User's ObjectId string.
            account_name: Account name from CSV.
            source_platform: Platform identifier.

        Returns:
            The account document (existing or new).
        """
        existing = self.find_one({
            "user_id": ObjectId(user_id),
            "account_name": account_name,
        })
        if existing:
            return existing

        from app.models.trade_account import (
            create_trade_account_doc,
        )

        doc = create_trade_account_doc(
            user_id=ObjectId(user_id),
            account_name=account_name,
            source_platform=source_platform,
        )
        self.insert_one(doc)
        return self.find_one({
            "user_id": ObjectId(user_id),
            "account_name": account_name,
        })

    def update_account(
        self, account_id: str, updates: dict
    ) -> bool:
        """Update a trade account."""
        updates["updated_at"] = utc_now()
        return self.update_one(
            account_id, {"$set": updates}
        )
