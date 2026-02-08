"""Tests for symbol mapper and market data service."""

from unittest.mock import patch
from datetime import date

import pytest
import pandas as pd

from app.market_data.symbol_mapper import map_to_yahoo
from app.market_data.service import MarketDataService


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


class TestMarketDataService:
    """Tests for MarketDataService with mocked yfinance."""

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

        with app.app_context():
            service = MarketDataService()
            ohlc = service.get_ohlc(
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

        with app.app_context():
            service = MarketDataService()
            # First call — fetches from yfinance
            ohlc1 = service.get_ohlc(
                symbol="MES",
                interval="5m",
                start="2026-01-05",
                end="2026-01-05",
            )
            call_count_1 = mock_yf.download.call_count

            # Second call — should use cache
            ohlc2 = service.get_ohlc(
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

        with app.app_context():
            service = MarketDataService()
            ohlc = service.get_ohlc(
                symbol="MES",
                interval="5m",
                start="2026-01-05",
                end="2026-01-05",
            )

        assert ohlc == []
