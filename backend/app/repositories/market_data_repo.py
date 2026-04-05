"""Market-data dataset metadata repository."""

from collections.abc import Iterable
from typing import Any, List
from datetime import date, datetime

from bson import ObjectId

from app.repositories.base import BaseRepository


class MarketDataRepository(BaseRepository):
    """Repository for market_data_datasets collection."""

    collection_name = "market_data_datasets"

    @staticmethod
    def _to_datetime(d):
        """Convert date to datetime for MongoDB."""
        if isinstance(d, date) and not isinstance(
            d, datetime
        ):
            return datetime(d.year, d.month, d.day)
        return d

    @staticmethod
    def _normalize_symbol_filters(
        symbols: str | Iterable[str],
    ) -> list[str]:
        """Normalize symbol filters into a unique ordered list."""

        if isinstance(symbols, str):
            values = [symbols]
        else:
            values = list(symbols)

        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value or value in seen:
                continue
            normalized.append(value)
            seen.add(value)
        return normalized

    @staticmethod
    def _symbol_priority(
        value: str,
        ordered_values: list[str],
    ) -> int:
        """Return the priority index for the given symbol."""

        try:
            return ordered_values.index(value)
        except ValueError:
            return len(ordered_values)

    def _dedupe_documents_by_symbol_priority(
        self,
        documents: list[dict],
        symbol_order: list[str],
        *,
        key_builder,
    ) -> list[dict]:
        """Keep the highest-priority symbol variant per logical dataset."""

        selected: dict[Any, dict] = {}
        for document in documents:
            key = key_builder(document)
            existing = selected.get(key)
            if existing is None:
                selected[key] = document
                continue

            if self._symbol_priority(
                document.get("symbol", ""),
                symbol_order,
            ) < self._symbol_priority(
                existing.get("symbol", ""),
                symbol_order,
            ):
                selected[key] = document

        return list(selected.values())

    def find_cached(
        self,
        symbol: str | Iterable[str],
        interval: str,
        start_date,
        end_date,
    ) -> List[dict]:
        """Return candle dataset metadata for a date range."""
        symbols = self._normalize_symbol_filters(symbol)
        if not symbols:
            return []

        documents = self.find_many(
            {
                "symbol": {"$in": symbols},
                "dataset_type": "candles",
                "timeframe": interval,
                "status": "ready",
                "date": {
                    "$gte": self._to_datetime(
                        start_date
                    ),
                    "$lte": self._to_datetime(end_date),
                },
            },
            sort=[("date", 1), ("symbol", 1)],
        )
        deduped = self._dedupe_documents_by_symbol_priority(
            documents,
            symbols,
            key_builder=lambda document: document["date"],
        )
        deduped.sort(key=lambda document: document["date"])
        return deduped

    def upsert_cache(
        self,
        symbol: str,
        interval: str,
        cache_date,
        ohlc: list,
        bar_count: int,
    ) -> None:
        """Retained for compatibility; use upsert_dataset_document."""
        raise NotImplementedError(
            "Embedded OHLC cache is no longer supported."
        )

    def has_cached_day(
        self,
        symbol: str | Iterable[str],
        interval: str,
        cache_date,
    ) -> bool:
        """Return True if candle metadata exists for symbol/day."""
        dt = self._to_datetime(cache_date)
        symbols = self._normalize_symbol_filters(symbol)
        if not symbols:
            return False

        doc = self.find_one(
            {
                "symbol": {"$in": symbols},
                "dataset_type": "candles",
                "timeframe": interval,
                "date": dt,
                "status": "ready",
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
        """Delete candle metadata for a date range."""
        result = self.collection.delete_many(
            {
                "symbol": symbol,
                "dataset_type": "candles",
                "timeframe": interval,
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
        """Return dataset metadata slices for the given symbols and dates."""
        symbols = self._normalize_symbol_filters(symbols)
        cache_dates = [self._to_datetime(day) for day in cache_dates]
        if not symbols or not cache_dates:
            return []
        documents = self.find_many(
            {
                "symbol": {"$in": symbols},
                "date": {"$in": cache_dates},
                "status": "ready",
            },
            sort=[
                ("symbol", 1),
                ("dataset_type", 1),
                ("timeframe", 1),
                ("date", 1),
            ],
        )
        deduped = self._dedupe_documents_by_symbol_priority(
            documents,
            symbols,
            key_builder=lambda document: (
                document["dataset_type"],
                document.get("timeframe"),
                document["date"],
            ),
        )
        deduped.sort(
            key=lambda document: (
                document["symbol"],
                document["dataset_type"],
                document.get("timeframe") or "",
                document["date"],
            )
        )
        return deduped

    def find_dataset(
        self,
        symbol: str | Iterable[str],
        dataset_type: str,
        dataset_date,
        timeframe: str | None = None,
    ) -> dict | None:
        """Return one dataset metadata document by its natural key."""
        symbols = self._normalize_symbol_filters(symbol)
        if not symbols:
            return None

        documents = self.find_many(
            {
                "symbol": {"$in": symbols},
                "dataset_type": dataset_type,
                "timeframe": timeframe,
                "date": self._to_datetime(dataset_date),
                "status": "ready",
            }
        )
        if not documents:
            return None

        documents.sort(
            key=lambda document: self._symbol_priority(
                document.get("symbol", ""),
                symbols,
            )
        )
        return documents[0]

    def find_saved_day_documents(self) -> List[dict]:
        """Return ready dataset metadata ordered for saved-day summaries."""

        return self.find_many(
            {"status": "ready"},
            sort=[
                ("date", -1),
                ("symbol", 1),
                ("dataset_type", 1),
                ("timeframe", 1),
                ("updated_at", -1),
            ],
            projection={
                "_id": 0,
                "symbol": 1,
                "raw_symbol": 1,
                "dataset_type": 1,
                "timeframe": 1,
                "date": 1,
                "updated_at": 1,
            },
        )

    def find_documents_for_saved_day(
        self,
        *,
        symbol: str,
        trading_day: date,
    ) -> List[dict]:
        """Return all ready dataset documents for one saved-day group."""

        return self.find_many(
            {
                "symbol": symbol,
                "date": self._to_datetime(trading_day),
                "status": "ready",
            },
            sort=[
                ("dataset_type", 1),
                ("timeframe", 1),
                ("created_at", 1),
            ],
        )

    def delete_documents_by_ids(
        self,
        document_ids: Iterable[ObjectId],
    ) -> int:
        """Delete multiple dataset documents by ObjectId."""

        normalized_ids = list(document_ids)
        if not normalized_ids:
            return 0

        return self.delete_many(
            {"_id": {"$in": normalized_ids}}
        )

    def upsert_document(self, document: dict) -> None:
        """Upsert a full dataset document by its natural key."""
        from app.utils.datetime_utils import utc_now

        self.collection.update_one(
            {
                "symbol": document["symbol"],
                "dataset_type": document["dataset_type"],
                "timeframe": document.get("timeframe"),
                "date": self._to_datetime(document["date"]),
            },
            {
                "$set": {
                    "raw_symbol": document.get("raw_symbol"),
                    "object_key": document["object_key"],
                    "row_count": document.get("row_count", 0),
                    "byte_size": document.get("byte_size", 0),
                    "source_file_name": document.get(
                        "source_file_name", ""
                    ),
                    "import_batch_id": document.get(
                        "import_batch_id"
                    ),
                    "status": document.get("status", "ready"),
                    "updated_at": document.get(
                        "updated_at", utc_now()
                    ),
                },
                "$setOnInsert": {
                    "created_at": document.get(
                        "created_at", utc_now()
                    ),
                }
            },
            upsert=True,
        )
