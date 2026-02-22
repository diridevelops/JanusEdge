"""Market data cache repository."""

from typing import List, Optional
from datetime import date, datetime

from app.repositories.base import BaseRepository


class MarketDataRepository(BaseRepository):
    """Repository for market_data_cache collection."""

    collection_name = "market_data_cache"

    @staticmethod
    def _to_datetime(d):
        """Convert date to datetime for MongoDB."""
        if isinstance(d, date) and not isinstance(
            d, datetime
        ):
            return datetime(d.year, d.month, d.day)
        return d

    def find_cached(
        self,
        symbol: str,
        interval: str,
        start_date,
        end_date,
    ) -> List[dict]:
        """
        Find cached OHLC data for a date range.

        Parameters:
            symbol: yfinance ticker.
            interval: Time interval.
            start_date: Start date.
            end_date: End date.

        Returns:
            List of cached data documents.
        """
        return self.find_many(
            {
                "symbol": symbol,
                "interval": interval,
                "date": {
                    "$gte": self._to_datetime(
                        start_date
                    ),
                    "$lte": self._to_datetime(end_date),
                },
            },
            sort=[("date", 1)],
        )

    def upsert_cache(
        self,
        symbol: str,
        interval: str,
        cache_date,
        ohlc: list,
        bar_count: int,
    ) -> None:
        """
        Insert or update cached OHLC data.

        Parameters:
            symbol: yfinance ticker.
            interval: Time interval.
            cache_date: The trading day.
            ohlc: List of OHLC dicts.
            bar_count: Number of candles.
        """
        from app.utils.datetime_utils import utc_now

        dt = self._to_datetime(cache_date)
        self.collection.update_one(
            {
                "symbol": symbol,
                "interval": interval,
                "date": dt,
            },
            {
                "$set": {
                    "ohlc": ohlc,
                    "bar_count": bar_count,
                    "fetched_at": utc_now(),
                    "source": "yfinance",
                }
            },
            upsert=True,
        )

    def has_cached_day(
        self,
        symbol: str,
        interval: str,
        cache_date,
    ) -> bool:
        """Return True if cached data exists for symbol/interval/day."""
        dt = self._to_datetime(cache_date)
        doc = self.find_one(
            {
                "symbol": symbol,
                "interval": interval,
                "date": dt,
            }
        )
        return doc is not None
