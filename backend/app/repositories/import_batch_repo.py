"""Import batch repository for database operations."""

from typing import List, Optional

from bson import ObjectId

from app.repositories.base import BaseRepository


class ImportBatchRepository(BaseRepository):
    """Repository for import_batches collection."""

    collection_name = "import_batches"

    def find_by_user(
        self, user_id: str
    ) -> List[dict]:
        """Find all import batches for a user."""
        return self.find_many(
            {"user_id": ObjectId(user_id)},
            sort=[("imported_at", -1)],
        )

    def find_by_file_hash(
        self, user_id: str, file_hash: str
    ) -> Optional[dict]:
        """
        Check if a file has already been imported.

        Parameters:
            user_id: User's ObjectId string.
            file_hash: SHA-256 hash of file.

        Returns:
            Import batch doc or None.
        """
        return self.find_one({
            "user_id": ObjectId(user_id),
            "file_hash": file_hash,
        })
