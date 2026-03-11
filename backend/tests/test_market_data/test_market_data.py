"""Tests for symbol mapper and market data service."""

from unittest.mock import patch
from datetime import date
from uuid import uuid4

import pytest
import pandas as pd

from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
    map_to_yahoo,
)
from app.market_data.service import MarketDataService
from app.models.user import create_user_doc


class TestSymbolMapper:
    """Tests for symbol mapping."""

    def test_ninjatrader_mes(self):
        assert (
            map_to_yahoo("MES", "MES 03-26") == "MES=F"
        )

    def test_ninjatrader_es(self):
        assert (
            map_to_yahoo("ES", "ES 03-26") == "ES=F"
        )

    def test_quantower_mes(self):
        assert (
            map_to_yahoo("MES", "MESM25") == "MES=F"
        )

    def test_quantower_nq(self):
        assert (
            map_to_yahoo("NQ", "NQH26") == "NQ=F"
        )

    def test_base_symbol_fallback(self):
        assert map_to_yahoo("MES") == "MES=F"

    def test_unknown_symbol_gets_futures_suffix(self):
        assert map_to_yahoo("ZB") == "ZB=F"

    def test_custom_mapping_overrides_default(self):
        symbol_mappings = get_default_symbol_mappings()
        symbol_mappings["MES"] = {
            "yahoo_symbol": "MES-CUSTOM=F",
            "dollar_value_per_point": 7.5,
        }

        assert (
            map_to_yahoo(
                "MES",
                "MES 03-26",
                symbol_mappings,
            )
            == "MES-CUSTOM=F"
        )

    def test_longest_prefix_match_prefers_longer_base_symbol(self):
        symbol_mappings = get_default_symbol_mappings()
        symbol_mappings["ME"] = {
            "yahoo_symbol": "ME=F",
            "dollar_value_per_point": 1.0,
        }

        assert (
            map_to_yahoo(
                "MES",
                "MESM25",
                symbol_mappings,
            )
            == "MES=F"
        )


class TestMarketDataService:
    """Tests for MarketDataService with mocked yfinance."""

    def _create_user(
        self,
        app,
        symbol_mappings: dict | None = None,
    ) -> str:
        """Insert a user for market data service tests."""
        from app.extensions import mongo

        with app.app_context():
            result = mongo.db.users.insert_one(
                create_user_doc(
                    username=(
                        f"market-data-user-{uuid4().hex}"
                    ),
                    password_hash="hashed",
                    timezone="America/New_York",
                    symbol_mappings=symbol_mappings,
                )
            )
        return str(result.inserted_id)

    @patch("app.market_data.service.yf")
    def test_fetch_returns_ohlc(self, mock_yf, app):
        """Test fetching data from yfinance 1.1.0."""
        # yfinance 1.1.0 with multi_level_index=False
        # returns flat column names.
        idx = pd.DatetimeIndex([
            "2026-01-05 10:00:00",
            "2026-01-05 10:05:00",
        ])
        data = pd.DataFrame(
            {
                "Open": [5000.0, 5005.0],
                "High": [5010.0, 5015.0],
                "Low": [4990.0, 4995.0],
                "Close": [5005.0, 5010.0],
                "Volume": [100.0, 150.0],
            },
            index=idx,
        )
        mock_yf.download.return_value = data
        user_id = self._create_user(app)

        with app.app_context():
            service = MarketDataService()
            ohlc = service.get_ohlc(
            user_id=user_id,
                symbol="MES",
                interval="5m",
                start="2026-01-05",
                end="2026-01-05",
            )

        assert len(ohlc) == 2
        assert ohlc[0]["open"] == 5000.0
        assert ohlc[1]["close"] == 5010.0

    @patch("app.market_data.service.yf")
    def test_cache_hit_avoids_yfinance(
        self, mock_yf, app
    ):
        """Second request should serve from cache."""
        idx = pd.DatetimeIndex([
            "2026-01-05 10:00:00",
        ])
        data = pd.DataFrame(
            {
                "Open": [5000.0],
                "High": [5010.0],
                "Low": [4990.0],
                "Close": [5005.0],
                "Volume": [100.0],
            },
            index=idx,
        )
        mock_yf.download.return_value = data
        user_id = self._create_user(app)

        with app.app_context():
            service = MarketDataService()
            # First call — fetches from yfinance
            ohlc1 = service.get_ohlc(
            user_id=user_id,
                symbol="MES",
                interval="5m",
                start="2026-01-05",
                end="2026-01-05",
            )
            call_count_1 = mock_yf.download.call_count

            # Second call — should use cache
            ohlc2 = service.get_ohlc(
                user_id=user_id,
                symbol="MES",
                interval="5m",
                start="2026-01-05",
                end="2026-01-05",
            )
            call_count_2 = mock_yf.download.call_count

        assert len(ohlc1) > 0
        assert len(ohlc2) > 0
        # yfinance should not be called a second time
        assert call_count_2 == call_count_1

    @patch("app.market_data.service.yf")
    def test_empty_data_returns_empty(
        self, mock_yf, app
    ):
        """Empty yfinance response returns empty list."""
        mock_yf.download.return_value = pd.DataFrame()
        user_id = self._create_user(app)

        with app.app_context():
            service = MarketDataService()
            ohlc = service.get_ohlc(
                user_id=user_id,
                symbol="MES",
                interval="5m",
                start="2026-01-05",
                end="2026-01-05",
            )

        assert ohlc == []

    @patch("app.market_data.service.yf")
    def test_fetch_uses_user_symbol_mappings(
        self, mock_yf, app
    ):
        """Service resolves yfinance tickers from user settings."""
        mock_yf.download.return_value = pd.DataFrame()
        symbol_mappings = get_default_symbol_mappings()
        symbol_mappings["MES"] = {
            "yahoo_symbol": "MES-CUSTOM=F",
            "dollar_value_per_point": 7.5,
        }
        user_id = self._create_user(app, symbol_mappings)

        with app.app_context():
            service = MarketDataService()
            service.get_ohlc(
                user_id=user_id,
                symbol="MES",
                raw_symbol="MES 03-26",
                interval="5m",
                start="2026-01-05",
                end="2026-01-05",
            )

        assert (
            mock_yf.download.call_args.kwargs["tickers"]
            == "MES-CUSTOM=F"
        )
