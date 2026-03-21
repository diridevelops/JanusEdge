"""Market-data service backed by imported tick-derived candles."""

import datetime as dt
from datetime import timedelta
from typing import List

from bson import ObjectId

from app.market_data.symbol_mapper import (
    get_effective_market_data_mappings,
)
from app.repositories.market_data_repo import MarketDataRepository
from app.repositories.user_repo import UserRepository
from app.tick_data.service import TickDataService


class MarketDataService:
    """Service for OHLC market data backed by stored Parquet datasets."""

    def __init__(self):
        self.dataset_repo = MarketDataRepository()
        self.tick_data_service = TickDataService()
        self.user_repo = UserRepository()

    def get_ohlc(
        self,
        user_id: str,
        symbol: str,
        interval: str = "5m",
        start: str = None,
        end: str = None,
        raw_symbol: str = None,
        force_refresh: bool = False,
    ) -> List[dict]:
        """
        Get OHLC candlestick data.

        Parameters:
            user_id: The requesting user's ObjectId string.
            symbol: Normalized symbol.
            interval: '1m', '5m', '15m', '1h', '1d'.
            start: Start date ISO string.
            end: End date ISO string.
            raw_symbol: Original platform symbol.
            force_refresh: If True, regenerate candles from stored ticks.

        Returns:
            List of OHLC dicts with time, open,
            high, low, close, volume.
        """
        start_dt = (
            dt.datetime.fromisoformat(start)
            if start
            else dt.datetime.now(dt.timezone.utc)
            - timedelta(days=7)
        )
        end_dt = (
            dt.datetime.fromisoformat(end)
            if end
            else dt.datetime.now(dt.timezone.utc)
        )

        # Ensure tz-aware (assume UTC if naive)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(
                tzinfo=dt.timezone.utc
            )
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(
                tzinfo=dt.timezone.utc
            )

        start_date = start_dt.date()
        end_date = end_dt.date()

        user = None
        if ObjectId.is_valid(user_id):
            user = self.user_repo.find_by_id(user_id)
        market_data_mappings = (
            get_effective_market_data_mappings(
                user.get("market_data_mappings")
                if user
                else None
            )
        )

        if force_refresh:
            self.tick_data_service.refresh_ohlc(
                symbol=symbol,
                raw_symbol=raw_symbol,
                start_date=start_date,
                end_date=end_date,
                market_data_mappings=market_data_mappings,
            )

        return self.tick_data_service.get_ohlc(
            symbol=symbol,
            raw_symbol=raw_symbol,
            interval=interval,
            start_dt=start_dt,
            end_dt=end_dt,
            market_data_mappings=market_data_mappings,
        )

    def list_saved_days(self, user_id: str) -> List[dict]:
        """Return saved market-data day summaries ordered by date."""

        del user_id

        summaries: dict[tuple[str, dt.date], dict] = {}
        for document in self.dataset_repo.find_saved_day_documents():
            document_date = document["date"]
            if isinstance(document_date, dt.datetime):
                trading_day = document_date.date()
            else:
                trading_day = document_date

            summary_key = (document["symbol"], trading_day)
            summary = summaries.get(summary_key)
            if summary is None:
                summary = {
                    "date": trading_day.isoformat(),
                    "symbol": document["symbol"],
                    "raw_symbol": document.get("raw_symbol"),
                    "available_timeframes": [],
                    "has_ticks": False,
                    "updated_at": self._serialize_datetime(
                        document.get("updated_at")
                    ),
                }
                summaries[summary_key] = summary

            raw_symbol = document.get("raw_symbol")
            if summary["raw_symbol"] is None and raw_symbol:
                summary["raw_symbol"] = raw_symbol

            if document.get("dataset_type") == "ticks":
                summary["has_ticks"] = True

            timeframe = document.get("timeframe")
            if (
                document.get("dataset_type") == "candles"
                and timeframe
                and timeframe not in summary["available_timeframes"]
            ):
                summary["available_timeframes"].append(timeframe)

            updated_at = self._serialize_datetime(
                document.get("updated_at")
            )
            if updated_at and (
                summary["updated_at"] is None
                or updated_at > summary["updated_at"]
            ):
                summary["updated_at"] = updated_at

        ordered_summaries = sorted(
            summaries.values(),
            key=lambda summary: (
                -dt.date.fromisoformat(summary["date"]).toordinal(),
                summary["symbol"],
            ),
        )
        for summary in ordered_summaries:
            summary["available_timeframes"].sort()

        return ordered_summaries

    @staticmethod
    def _serialize_datetime(value: dt.datetime | None) -> str | None:
        """Serialize datetimes to ISO-8601 strings."""

        if value is None:
            return None
        if value.tzinfo is None:
            return value.isoformat() + "+00:00"
        return value.isoformat()
