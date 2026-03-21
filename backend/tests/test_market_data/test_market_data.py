"""Tests for symbol resolution, saved days, and dataset-backed OHLC."""

from datetime import date, datetime, timezone
from uuid import uuid4

from app.market_data.service import MarketDataService
from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
    resolve_market_data_symbol,
    resolve_market_data_symbols,
)


def _register_and_login(client):
    """Register a test user and return authorization headers."""

    username = f"marketdata-{uuid4().hex}"

    register_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": "TestPass123!",
        },
    )
    token = response.get_json()["token"]
    return {
        "Authorization": f"Bearer {token}"
    }, register_response.get_json()["user"]["id"]


class TestSymbolMapper:
    """Tests for market-data symbol resolution."""

    def test_defaults_to_self_without_explicit_mapping(self):
        assert (
            resolve_market_data_symbol("MES", "MES 03-26")
            == "MES 03-26"
        )
        assert resolve_market_data_symbol("mes") == "MES"

    def test_applies_explicit_mapping_preserving_suffixes(self):
        market_data_mappings = {
            "M": "SHOULD_NOT_MATCH",
            "MES": "ES",
        }

        assert (
            resolve_market_data_symbol(
                "MES",
                "MES 03-26",
                market_data_mappings,
            )
            == "ES 03-26"
        )
        assert (
            resolve_market_data_symbol(
                "MES",
                "MESM26",
                market_data_mappings,
            )
            == "ESM26"
        )

    def test_returns_explicit_and_original_symbol_aliases(self):
        assert resolve_market_data_symbols(
            "MES",
            "MES 03-26",
            {"MES": "ES"},
        ) == [
            "ES 03-26",
            "MES 03-26",
            "ES",
            "MES",
        ]

    def test_default_symbol_mapping_keeps_point_values_only(self):
        mappings = get_default_symbol_mappings()

        assert mappings["MES"] == {"dollar_value_per_point": 5.0}


class TestMarketDataService:
    """Tests for reading and regenerating stored OHLC data."""

    def test_get_ohlc_reads_precomputed_candles(
        self,
        app,
        seed_market_data_dataset,
    ):
        trading_day = date(2026, 1, 5)
        seed_market_data_dataset(
            symbol="MES 03-26",
            raw_symbol="MES 03-26",
            dataset_type="candles",
            timeframe="5m",
            trading_day=trading_day,
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5006.0,
                    "low": 4998.0,
                    "close": 5004.0,
                    "volume": 10,
                },
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            5,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5004.0,
                    "high": 5008.0,
                    "low": 5002.0,
                    "close": 5007.0,
                    "volume": 12,
                },
            ],
        )

        with app.app_context():
            ohlc = MarketDataService().get_ohlc(
                user_id="ignored",
                symbol="MES",
                raw_symbol="MES 03-26",
                interval="5m",
                start="2026-01-05T10:00:00+00:00",
                end="2026-01-05T10:10:00+00:00",
            )

        assert len(ohlc) == 2
        assert ohlc[0]["open"] == 5000.0
        assert ohlc[1]["close"] == 5007.0

    def test_get_ohlc_reads_legacy_symbol_dataset_via_alias_lookup(
        self,
        app,
        client,
        seed_market_data_dataset,
    ):
        headers, user_id = _register_and_login(client)
        update_response = client.put(
            "/api/auth/market-data-mappings",
            headers=headers,
            json={"market_data_mappings": {"MES": "ES"}},
        )
        assert update_response.status_code == 200

        trading_day = date(2026, 1, 5)
        seed_market_data_dataset(
            symbol="ES 03-26",
            raw_symbol="ES 03-26",
            dataset_type="candles",
            timeframe="5m",
            trading_day=trading_day,
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5006.0,
                    "low": 4998.0,
                    "close": 5004.0,
                    "volume": 10,
                }
            ],
        )

        with app.app_context():
            ohlc = MarketDataService().get_ohlc(
                user_id=user_id,
                symbol="MES",
                raw_symbol="MES 03-26",
                interval="5m",
                start="2026-01-05T10:00:00+00:00",
                end="2026-01-05T10:05:00+00:00",
            )

        assert len(ohlc) == 1
        assert ohlc[0]["close"] == 5004.0

    def test_force_refresh_regenerates_candles_from_ticks(
        self,
        app,
        client,
        seed_market_data_dataset,
    ):
        headers, user_id = _register_and_login(client)
        update_response = client.put(
            "/api/auth/market-data-mappings",
            headers=headers,
            json={"market_data_mappings": {"MES": "ES"}},
        )
        assert update_response.status_code == 200

        trading_day = date(2026, 1, 5)
        seed_market_data_dataset(
            symbol="ES 03-26",
            raw_symbol="ES 03-26",
            dataset_type="ticks",
            trading_day=trading_day,
            rows=[
                {
                    "timestamp": "2026-01-05T10:00:00+00:00",
                    "last_price": 5000.0,
                    "bid_price": 4999.75,
                    "ask_price": 5000.25,
                    "size": 1,
                },
                {
                    "timestamp": "2026-01-05T10:02:00+00:00",
                    "last_price": 5003.0,
                    "bid_price": 5002.75,
                    "ask_price": 5003.25,
                    "size": 2,
                },
                {
                    "timestamp": "2026-01-05T10:04:00+00:00",
                    "last_price": 5001.0,
                    "bid_price": 5000.75,
                    "ask_price": 5001.25,
                    "size": 3,
                },
            ],
        )
        seed_market_data_dataset(
            symbol="ES 03-26",
            raw_symbol="ES 03-26",
            dataset_type="candles",
            timeframe="5m",
            trading_day=trading_day,
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "volume": 1,
                }
            ],
        )

        with app.app_context():
            ohlc = MarketDataService().get_ohlc(
                user_id=user_id,
                symbol="MES",
                raw_symbol="MES 03-26",
                interval="5m",
                start="2026-01-05T10:00:00+00:00",
                end="2026-01-05T10:05:00+00:00",
                force_refresh=True,
            )

        assert ohlc == [
            {
                "time": int(
                    datetime(
                        2026,
                        1,
                        5,
                        10,
                        0,
                        tzinfo=timezone.utc,
                    ).timestamp()
                ),
                "open": 5000.0,
                "high": 5003.0,
                "low": 5000.0,
                "close": 5001.0,
                "volume": 6,
            }
        ]

    def test_get_ohlc_returns_empty_when_no_dataset_exists(
        self,
        app,
    ):
        with app.app_context():
            ohlc = MarketDataService().get_ohlc(
                user_id="ignored",
                symbol="MES",
                raw_symbol="MES 03-26",
                interval="5m",
                start="2026-01-05T10:00:00+00:00",
                end="2026-01-05T10:05:00+00:00",
            )

        assert ohlc == []


class TestMarketDataRoutes:
    """Tests for authenticated market-data summary routes."""

    def test_saved_days_returns_symbol_date_summaries(
        self,
        client,
        seed_market_data_dataset,
    ):
        headers, _ = _register_and_login(client)

        seed_market_data_dataset(
            symbol="ES 06-26",
            raw_symbol="ES 06-26",
            dataset_type="ticks",
            trading_day=date(2026, 1, 6),
            rows=[
                {
                    "timestamp": "2026-01-06T14:30:00+00:00",
                    "last_price": 5000.0,
                    "bid_price": 4999.75,
                    "ask_price": 5000.25,
                    "size": 1,
                }
            ],
        )
        seed_market_data_dataset(
            symbol="ES 06-26",
            raw_symbol="ES 06-26",
            dataset_type="candles",
            timeframe="1m",
            trading_day=date(2026, 1, 6),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            6,
                            14,
                            30,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5001.0,
                    "low": 4999.0,
                    "close": 5000.5,
                    "volume": 2,
                }
            ],
        )
        seed_market_data_dataset(
            symbol="ES 06-26",
            raw_symbol="ES 06-26",
            dataset_type="candles",
            timeframe="5m",
            trading_day=date(2026, 1, 6),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            6,
                            14,
                            30,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5002.0,
                    "low": 4999.0,
                    "close": 5001.0,
                    "volume": 5,
                }
            ],
        )
        seed_market_data_dataset(
            symbol="NQ 06-26",
            raw_symbol="NQ 06-26",
            dataset_type="candles",
            timeframe="1m",
            trading_day=date(2026, 1, 5),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            14,
                            30,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 21000.0,
                    "high": 21010.0,
                    "low": 20990.0,
                    "close": 21005.0,
                    "volume": 3,
                }
            ],
        )

        response = client.get(
            "/api/market-data/saved-days",
            headers=headers,
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["saved_days"] == [
            {
                "date": "2026-01-06",
                "symbol": "ES 06-26",
                "raw_symbol": "ES 06-26",
                "available_timeframes": ["1m", "5m"],
                "has_ticks": True,
                "updated_at": payload["saved_days"][0]["updated_at"],
            },
            {
                "date": "2026-01-05",
                "symbol": "NQ 06-26",
                "raw_symbol": "NQ 06-26",
                "available_timeframes": ["1m"],
                "has_ticks": False,
                "updated_at": payload["saved_days"][1]["updated_at"],
            },
        ]
        assert payload["saved_days"][0]["updated_at"].endswith(
            "+00:00"
        )
