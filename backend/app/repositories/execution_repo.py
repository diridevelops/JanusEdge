"""Execution repository for database operations."""

from typing import List

from bson import ObjectId

from app.repositories.base import BaseRepository


class ExecutionRepository(BaseRepository):
    """Repository for executions collection."""

    collection_name = "executions"

    def find_by_trade(
        self, trade_id: str
    ) -> List[dict]:
        """
        Find all executions for a trade.

        Parameters:
            trade_id: Trade's ObjectId string.

        Returns:
            List of execution documents sorted by timestamp.
        """
        return self.find_many(
            {"trade_id": ObjectId(trade_id)},
            sort=[("timestamp", 1)],
        )

    def find_by_user(
        self,
        user_id: str,
        filters: dict = None,
        skip: int = 0,
        limit: int = 25,
    ) -> List[dict]:
        """
        Find executions for a user with optional filters.

        Parameters:
            user_id: User's ObjectId string.
            filters: Additional query conditions.
            skip: Number to skip.
            limit: Max results.

        Returns:
            List of execution dicts.
        """
        query = {"user_id": ObjectId(user_id)}
        if filters:
            query.update(filters)
        return self.find_many(
            query,
            sort=[("timestamp", -1)],
            skip=skip,
            limit=limit,
        )

    def count_by_user(
        self, user_id: str, filters: dict = None
    ) -> int:
        """Count executions for a user."""
        query = {"user_id": ObjectId(user_id)}
        if filters:
            query.update(filters)
        return self.count(query)

    def find_by_batch(
        self, batch_id: str
    ) -> List[dict]:
        """Find all executions for an import batch."""
        return self.find_many(
            {"import_batch_id": ObjectId(batch_id)},
            sort=[("timestamp", 1)],
        )

    def count_by_batch(self, batch_id: str) -> int:
        """Count executions for an import batch."""
        return self.count(
            {"import_batch_id": ObjectId(batch_id)}
        )

    def update_trade_ids(
        self, execution_ids: List[str], trade_id: str
    ) -> int:
        """
        Set trade_id on multiple executions.

        Parameters:
            execution_ids: List of execution ObjectId strings.
            trade_id: Trade ObjectId string.

        Returns:
            Number of documents modified.
        """
        result = self.collection.update_many(
            {
                "_id": {
                    "$in": [
                        ObjectId(eid) for eid in execution_ids
                    ]
                }
            },
            {"$set": {"trade_id": ObjectId(trade_id)}},
        )
        return result.modified_count

    def find_by_trade_ids(
        self, trade_ids: List[ObjectId]
    ) -> List[dict]:
        """Find all executions for a set of trades."""
        if not trade_ids:
            return []
        return self.find_many(
            {"trade_id": {"$in": list(trade_ids)}},
            sort=[("timestamp", 1)],
        )
