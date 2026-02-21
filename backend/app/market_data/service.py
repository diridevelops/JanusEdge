"""Market data service — yfinance 1.1.0 with MongoDB caching."""

import datetime as dt
from datetime import date, timedelta
from typing import List

import yfinance as yf

from app.market_data.symbol_mapper import map_to_yahoo
from app.repositories.market_data_repo import (
    MarketDataRepository,
)
from app.utils.errors import MarketDataError


class MarketDataService:
    """Service for OHLC market data with caching."""

    def __init__(self):
        self.cache_repo = MarketDataRepository()

    def get_ohlc(
        self,
        symbol: str,
        interval: str = "5m",
        start: str = None,
        end: str = None,
        raw_symbol: str = None,
    ) -> List[dict]:
        """
        Get OHLC candlestick data.

        Checks cache first. On miss, fetches from yfinance
        and stores permanently.

        Parameters:
            symbol: Normalized symbol.
            interval: '1m', '5m', '15m', '1h', '1d'.
            start: Start date ISO string.
            end: End date ISO string.
            raw_symbol: Original platform symbol.

        Returns:
            List of OHLC dicts with time, open,
            high, low, close, volume.
        """
        yahoo_ticker = map_to_yahoo(
            symbol, raw_symbol
        )

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

        # Add 2-hours padding around the trade
        start_dt -= timedelta(hours=2)
        end_dt += timedelta(hours=2)

        start_date = start_dt.date()
        end_date = end_dt.date()

        # Check cache
        cached = self.cache_repo.find_cached(
            yahoo_ticker, interval, start_date, end_date
        )

        if cached:
            # Check coverage
            cached_dates = set()
            for doc in cached:
                d = doc["date"]
                if isinstance(d, dt.datetime):
                    cached_dates.add(d.date())
                else:
                    cached_dates.add(d)
            needed_dates = self._trading_dates(
                start_date, end_date
            )
            missing = needed_dates - cached_dates

            if not missing:
                # Full cache hit
                ohlc = []
                for doc in cached:
                    ohlc.extend(doc.get("ohlc", []))
                ohlc.sort(key=lambda x: x["time"])
                return ohlc

        # Fetch from yfinance
        ohlc_data = self._fetch_yfinance(
            yahoo_ticker, interval, start_dt, end_dt
        )

        # Group by date and cache
        self._cache_by_date(
            yahoo_ticker, interval, ohlc_data
        )

        return ohlc_data

    def _fetch_yfinance(
        self,
        ticker: str,
        interval: str,
        start_dt: dt.datetime,
        end_dt: dt.datetime,
    ) -> List[dict]:
        """
        Fetch OHLC from yfinance 1.1.0.

        Uses tz-aware UTC datetimes for start/end and
        multi_level_index=False to get flat column names.

        Parameters:
            ticker: yfinance ticker string.
            interval: Time interval.
            start_dt: Start datetime (tz-aware UTC).
            end_dt: End datetime (tz-aware UTC).

        Returns:
            List of OHLC dicts.
        """
        try:
            data = yf.download(
                tickers=ticker,
                start=start_dt,
                end=end_dt,
                interval=interval,
                prepost=False,
                progress=False,
                timeout=10,
                multi_level_index=False,
            )

            if data.empty:
                return []

            ohlc = []
            for idx, row in data.iterrows():
                ts = idx
                if hasattr(ts, "timestamp"):
                    time_val = int(ts.timestamp())
                else:
                    time_val = int(
                        dt.datetime.combine(
                            ts, dt.time.min
                        ).timestamp()
                    )

                ohlc.append({
                    "time": time_val,
                    "open": round(
                        float(row["Open"]), 6
                    ),
                    "high": round(
                        float(row["High"]), 6
                    ),
                    "low": round(
                        float(row["Low"]), 6
                    ),
                    "close": round(
                        float(row["Close"]), 6
                    ),
                    "volume": int(
                        float(row.get("Volume", 0))
                    ),
                })

            return ohlc

        except Exception as e:
            raise MarketDataError(
                f"Failed to fetch market data: {str(e)}"
            )

    def _cache_by_date(
        self,
        ticker: str,
        interval: str,
        ohlc_data: List[dict],
    ) -> None:
        """Cache OHLC data grouped by date."""
        if not ohlc_data:
            return

        grouped = {}
        for bar in ohlc_data:
            bar_date = date.fromtimestamp(bar["time"])
            if bar_date not in grouped:
                grouped[bar_date] = []
            grouped[bar_date].append(bar)

        for bar_date, bars in grouped.items():
            self.cache_repo.upsert_cache(
                symbol=ticker,
                interval=interval,
                cache_date=bar_date,
                ohlc=bars,
                bar_count=len(bars),
            )

    def _trading_dates(
        self, start: date, end: date
    ) -> set:
        """
        Generate potential trading dates
        (weekdays only) in a range.
        """
        dates = set()
        current = start
        while current <= end:
            if current.weekday() < 5:
                dates.add(current)
            current += timedelta(days=1)
        return dates
