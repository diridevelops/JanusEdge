"""Market data cache repository."""

from typing import Iterable, List
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

    def delete_cached_range(
        self,
        symbol: str,
        interval: str,
        start_date,
        end_date,
    ) -> int:
        """
        Delete cached OHLC data for a date range.

        Parameters:
            symbol: yfinance ticker.
            interval: Time interval.
            start_date: Start date.
            end_date: End date.

        Returns:
            Number of deleted documents.
        """
        result = self.collection.delete_many(
            {
                "symbol": symbol,
                "interval": interval,
                "date": {
                    "$gte": self._to_datetime(
                        start_date
                    ),
                    "$lte": self._to_datetime(
                        end_date
                    ),
                },
            }
        )
        return result.deleted_count

    def find_by_symbols_and_dates(
        self,
        symbols: Iterable[str],
        cache_dates: Iterable[date],
    ) -> List[dict]:
        """Return cached slices for the given symbols and dates."""
        symbols = list(symbols)
        cache_dates = [self._to_datetime(day) for day in cache_dates]
        if not symbols or not cache_dates:
            return []
        return self.find_many(
            {
                "symbol": {"$in": symbols},
                "date": {"$in": cache_dates},
            },
            sort=[("symbol", 1), ("interval", 1), ("date", 1)],
        )

    def upsert_document(self, document: dict) -> None:
        """Upsert a full cache document by its natural key."""
        self.collection.update_one(
            {
                "symbol": document["symbol"],
                "interval": document["interval"],
                "date": self._to_datetime(document["date"]),
            },
            {
                "$set": {
                    "ohlc": document.get("ohlc", []),
                    "bar_count": document.get("bar_count", 0),
                    "fetched_at": document.get("fetched_at"),
                    "source": document.get("source", "yfinance"),
                }
            },
            upsert=True,
        )
