"""Lifecycle coordination for durable Backtest preparation jobs."""

from __future__ import annotations

from datetime import date

from bson import ObjectId

from app.backtests.repository import PreparationJobRepository
from app.backtests.schemas import create_preparation_job_doc


class PreparationJobService:
    """Build and persist the one job associated with each new run."""

    def __init__(self, repository=None):
        self.repository = repository or PreparationJobRepository()

    def build_for_run(
        self,
        *,
        job_id: ObjectId,
        user_id: ObjectId,
        run_id: ObjectId,
        instrument: str,
        requested_start_date: date,
        requested_end_date: date,
        start_utc_date: date,
        end_utc_date: date,
        staging_prefix: str,
    ) -> dict:
        """Build a BSON-safe job with durable UTC-date recovery bounds."""
        return create_preparation_job_doc(
            job_id=job_id,
            user_id=user_id,
            run_id=run_id,
            instrument=instrument,
            requested_start_date=requested_start_date,
            requested_end_date=requested_end_date,
            start_utc_date=start_utc_date,
            end_utc_date=end_utc_date,
            staging_prefix=staging_prefix,
        )

    def create(self, document: dict) -> ObjectId:
        return self.repository.create(document)

    def requeue(self, run_id, *, now) -> bool:
        return self.repository.requeue(run_id, now=now)
