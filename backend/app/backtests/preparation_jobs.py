"""Lifecycle coordination for durable Backtest preparation jobs."""

from __future__ import annotations

from datetime import date

from bson import ObjectId

from app.backtests.fx_conversion import (
    build_conversion_spec,
    quote_currency_from_instrument,
)
from app.backtests.repository import PreparationJobRepository
from app.backtests.schemas import (
    create_preparation_job_doc,
    create_random_selection_job_doc,
)


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
        context_start_utc_date: date,
        end_utc_date: date,
        staging_prefix: str,
        quote_currency: str | None = None,
        conversion_spec: dict | None = None,
    ) -> dict:
        """Build a BSON-safe job with durable UTC-date recovery bounds."""
        document = create_preparation_job_doc(
            job_id=job_id,
            user_id=user_id,
            run_id=run_id,
            instrument=instrument,
            requested_start_date=requested_start_date,
            requested_end_date=requested_end_date,
            context_start_utc_date=context_start_utc_date,
            end_utc_date=end_utc_date,
            staging_prefix=staging_prefix,
        )
        return self._include_fx_conversion(
            document,
            instrument=instrument,
            quote_currency=quote_currency,
            conversion_spec=conversion_spec,
        )

    def create(self, document: dict) -> ObjectId:
        return self.repository.create(document)

    def build_for_random_selection(
        self,
        *,
        job_id: ObjectId,
        user_id: ObjectId,
        run_id: ObjectId,
        instrument: str,
        period_months: int,
        as_of_date: date,
        minimum_start_date: date,
        maximum_start_date: date,
        staging_prefix: str,
        blind_mode: bool = False,
        quote_currency: str | None = None,
        conversion_spec: dict | None = None,
    ) -> dict:
        """Build the durable selection phase before replay bounds exist."""
        document = create_random_selection_job_doc(
            job_id=job_id,
            user_id=user_id,
            run_id=run_id,
            instrument=instrument,
            period_months=period_months,
            as_of_date=as_of_date,
            minimum_start_date=minimum_start_date,
            maximum_start_date=maximum_start_date,
            staging_prefix=staging_prefix,
            blind_mode=blind_mode,
        )
        return self._include_fx_conversion(
            document,
            instrument=instrument,
            quote_currency=quote_currency,
            conversion_spec=conversion_spec,
        )

    def requeue(self, run_id, *, now) -> bool:
        return self.repository.requeue(run_id, now=now)

    @staticmethod
    def _include_fx_conversion(
        document: dict,
        *,
        instrument: str,
        quote_currency: str | None,
        conversion_spec: dict | None = None,
    ) -> dict:
        """Persist the conversion source contract before a worker claims the job."""
        currency = quote_currency or quote_currency_from_instrument(instrument)
        spec = (
            dict(conversion_spec)
            if isinstance(conversion_spec, dict)
            else build_conversion_spec(currency)
        )
        if spec is not None:
            document["fx_conversion"] = spec
        return document
