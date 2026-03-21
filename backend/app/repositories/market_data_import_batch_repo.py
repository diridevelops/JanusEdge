"""Repository for market-data import batch documents."""

from bson import ObjectId

from app.repositories.base import BaseRepository


class MarketDataImportBatchRepository(BaseRepository):
    """Repository for market_data_import_batches collection."""

    collection_name = "market_data_import_batches"

    def find_by_user_and_id(
        self,
        user_id: str,
        batch_id: str,
    ) -> dict | None:
        """Return one import batch for the authenticated user."""

        return self.find_one(
            {
                "_id": ObjectId(batch_id),
                "user_id": ObjectId(user_id),
            }
        )

    def mark_processing(self, batch_id: str) -> None:
        """Mark an import batch as actively processing."""

        from app.utils.datetime_utils import utc_now

        now = utc_now()
        self.collection.update_one(
            {"_id": ObjectId(batch_id)},
            {
                "$set": {
                    "status": "processing",
                    "started_at": now,
                    "updated_at": now,
                }
            },
        )

    def update_progress(
        self,
        batch_id: str,
        *,
        processed_bytes: int,
        total_bytes: int,
        processed_lines: int,
        valid_ticks: int,
        skipped_lines: int,
        days_completed: int,
        datasets_written: int,
    ) -> None:
        """Persist current import progress counters."""

        from app.utils.datetime_utils import utc_now

        percentage = 0.0
        if total_bytes > 0:
            percentage = round(
                min(processed_bytes / total_bytes, 1.0) * 100,
                2,
            )

        self.collection.update_one(
            {"_id": ObjectId(batch_id)},
            {
                "$set": {
                    "status": "processing",
                    "progress": {
                        "processed_bytes": processed_bytes,
                        "total_bytes": total_bytes,
                        "processed_percentage": percentage,
                    },
                    "stats": {
                        "processed_lines": processed_lines,
                        "valid_ticks": valid_ticks,
                        "skipped_lines": skipped_lines,
                        "days_completed": days_completed,
                        "datasets_written": datasets_written,
                    },
                    "updated_at": utc_now(),
                }
            },
        )

    def mark_completed(
        self,
        batch_id: str,
        *,
        total_bytes: int,
        processed_lines: int,
        valid_ticks: int,
        skipped_lines: int,
        days_completed: int,
        datasets_written: int,
    ) -> None:
        """Mark an import batch as completed."""

        from app.utils.datetime_utils import utc_now

        now = utc_now()
        self.collection.update_one(
            {"_id": ObjectId(batch_id)},
            {
                "$set": {
                    "status": "completed",
                    "progress": {
                        "processed_bytes": total_bytes,
                        "total_bytes": total_bytes,
                        "processed_percentage": 100.0,
                    },
                    "stats": {
                        "processed_lines": processed_lines,
                        "valid_ticks": valid_ticks,
                        "skipped_lines": skipped_lines,
                        "days_completed": days_completed,
                        "datasets_written": datasets_written,
                    },
                    "completed_at": now,
                    "updated_at": now,
                    "error_message": None,
                }
            },
        )

    def mark_failed(
        self,
        batch_id: str,
        *,
        error_message: str,
        processed_bytes: int,
        total_bytes: int,
        processed_lines: int,
        valid_ticks: int,
        skipped_lines: int,
        days_completed: int,
        datasets_written: int,
    ) -> None:
        """Mark an import batch as failed."""

        from app.utils.datetime_utils import utc_now

        percentage = 0.0
        if total_bytes > 0:
            percentage = round(
                min(processed_bytes / total_bytes, 1.0) * 100,
                2,
            )

        now = utc_now()
        self.collection.update_one(
            {"_id": ObjectId(batch_id)},
            {
                "$set": {
                    "status": "failed",
                    "progress": {
                        "processed_bytes": processed_bytes,
                        "total_bytes": total_bytes,
                        "processed_percentage": percentage,
                    },
                    "stats": {
                        "processed_lines": processed_lines,
                        "valid_ticks": valid_ticks,
                        "skipped_lines": skipped_lines,
                        "days_completed": days_completed,
                        "datasets_written": datasets_written,
                    },
                    "error_message": error_message,
                    "completed_at": now,
                    "updated_at": now,
                }
            },
        )