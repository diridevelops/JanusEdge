"""Trade repository for database operations."""

from typing import Dict, List, Optional

from bson import ObjectId

from app.repositories.base import BaseRepository
from app.utils.datetime_utils import utc_now


class TradeRepository(BaseRepository):
    """Repository for trades collection."""

    collection_name = "trades"

    def find_by_user(
        self,
        user_id: str,
        filters: dict = None,
        sort_by: str = "entry_time",
        sort_dir: int = -1,
        skip: int = 0,
        limit: int = 25,
    ) -> List[dict]:
        """
        Find trades for a user with optional filters.

        Parameters:
            user_id: User's ObjectId string.
            filters: Additional query filters.
            sort_by: Field to sort by.
            sort_dir: 1 for asc, -1 for desc.
            skip: Number of results to skip.
            limit: Max number of results.

        Returns:
            List of trade documents.
        """
        query = {
            "user_id": ObjectId(user_id),
            "status": {"$ne": "deleted"},
        }
        if filters:
            query.update(filters)

        return self.find_many(
            query,
            sort=[(sort_by, sort_dir)],
            skip=skip,
            limit=limit,
        )

    def count_by_user(
        self, user_id: str, filters: dict = None
    ) -> int:
        """Count trades for a user with optional filters."""
        query = {
            "user_id": ObjectId(user_id),
            "status": {"$ne": "deleted"},
        }
        if filters:
            query.update(filters)
        return self.count(query)

    def soft_delete(self, trade_id: str) -> bool:
        """
        Soft-delete a trade by setting status to 'deleted'.

        Parameters:
            trade_id: Trade's ObjectId string.

        Returns:
            True if updated.
        """
        return self.update_one(
            trade_id,
            {
                "$set": {
                    "status": "deleted",
                    "deleted_at": utc_now(),
                    "updated_at": utc_now(),
                }
            },
        )

    def restore(self, trade_id: str) -> bool:
        """
        Restore a soft-deleted trade.

        Parameters:
            trade_id: Trade's ObjectId string.

        Returns:
            True if updated.
        """
        return self.update_one(
            trade_id,
            {
                "$set": {
                    "status": "closed",
                    "deleted_at": None,
                    "updated_at": utc_now(),
                }
            },
        )

    def search_text(
        self, user_id: str, query_text: str
    ) -> List[dict]:
        """
        Full-text search on trades.

        Parameters:
            user_id: User's ObjectId string.
            query_text: Search query.

        Returns:
            List of matching trade documents.
        """
        return self.find_many(
            {
                "user_id": ObjectId(user_id),
                "status": {"$ne": "deleted"},
                "$text": {"$search": query_text},
            },
            limit=50,
        )

    def distinct_symbols(
        self, user_id: str
    ) -> List[str]:
        """Return sorted distinct symbols for a user's closed trades."""
        symbols = self.collection.distinct(
            "symbol",
            {
                "user_id": ObjectId(user_id),
                "status": "closed",
            },
        )
        return sorted(symbols)
