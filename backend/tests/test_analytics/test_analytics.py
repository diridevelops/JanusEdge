"""Tests for analytics endpoints."""

from datetime import datetime, timedelta

import pytest
from bson import ObjectId

from app.extensions import mongo
from app.utils.datetime_utils import utc_now


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clear all collections before each test."""
    with app.app_context():
        mongo.db.users.delete_many({})
        mongo.db.trades.delete_many({})
        mongo.db.tags.delete_many({})


@pytest.fixture
def auth_headers(client):
    """Register and login a test user, return headers."""
    client.post(
        "/api/auth/register",
        json={
            "username": "analyticsuser",
            "password": "testpass123",
            "timezone": "America/New_York",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={
            "username": "analyticsuser",
            "password": "testpass123",
        },
    )
    token = resp.json["token"]
    return {"Authorization": f"Bearer {token}"}


def _get_user_id(app):
    """Retrieve the test user's ObjectId."""
    with app.app_context():
        user = mongo.db.users.find_one(
            {"username": "analyticsuser"}
        )
        return user["_id"]


def _insert_trade(
    app,
    user_id,
    net_pnl,
    gross_pnl=None,
    fee=0.0,
    entry_time=None,
    exit_time=None,
    symbol="MES",
    side="Long",
    tag_ids=None,
    status="closed",
):
    """Insert a trade document directly into MongoDB."""
    if gross_pnl is None:
        gross_pnl = net_pnl + fee
    if exit_time is None:
        exit_time = datetime(2025, 1, 15, 14, 30, 0)
    if entry_time is None:
        entry_time = exit_time - timedelta(minutes=30)

    trade_doc = {
        "user_id": user_id,
        "trade_account_id": ObjectId(),
        "import_batch_id": ObjectId(),
        "symbol": symbol,
        "raw_symbol": symbol,
        "side": side,
        "total_quantity": 1,
        "max_quantity": 1,
        "avg_entry_price": 5000.0,
        "avg_exit_price": 5000.0
        + (net_pnl + fee) / 5.0,
        "gross_pnl": gross_pnl,
        "fee": fee,
        "fee_source": "csv",
        "net_pnl": net_pnl,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "holding_time_seconds": int(
            (exit_time - entry_time).total_seconds()
        ),
        "execution_count": 2,
        "source": "imported",
        "status": status,
        "tag_ids": tag_ids or [],
        "strategy": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "deleted_at": None,
    }

    with app.app_context():
        mongo.db.trades.insert_one(trade_doc)
    return trade_doc


class TestAnalyticsSummary:
    """Tests for GET /api/analytics/summary."""

    def test_summary_no_trades(
        self, client, auth_headers
    ):
        """Summary returns zeros when no trades exist."""
        resp = client.get(
            "/api/analytics/summary",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json
        assert data["total_trades"] == 0
        assert data["win_rate"] == 0.0
        assert data["total_net_pnl"] == 0.0
        assert data["appt"] == 0.0
        assert data["pl_ratio"] is None
        assert data["win_per_share_avg"] == 0.0
        assert data["loss_per_share_avg"] == 0.0

    def test_summary_basic(
        self, app, client, auth_headers
    ):
        """Summary computes correct metrics."""
        user_id = _get_user_id(app)

        # Insert 5 trades: 3 winners, 1 loser, 1 BE
        base = datetime(2025, 1, 15, 10, 0, 0)
        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            fee=2.0,
            exit_time=base + timedelta(hours=1),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=50.0,
            fee=2.0,
            exit_time=base + timedelta(hours=2),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=75.0,
            fee=2.0,
            exit_time=base + timedelta(hours=3),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-80.0,
            fee=2.0,
            exit_time=base + timedelta(hours=4),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=0.0,
            fee=2.0,
            exit_time=base + timedelta(hours=5),
        )

        resp = client.get(
            "/api/analytics/summary",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert data["total_trades"] == 5
        assert data["winners"] == 3
        assert data["losers"] == 1
        assert data["breakeven"] == 1
        assert data["win_rate"] == 60.0
        assert data["total_net_pnl"] == 145.0
        assert data["total_fees"] == 10.0

        # avg winner = (100+50+75)/3 = 75.0
        assert data["avg_winner"] == 75.0
        # avg loser = -80/1 = -80.0
        assert data["avg_loser"] == -80.0
        # largest win = 100
        assert data["largest_win"] == 100.0
        # largest loss = -80
        assert data["largest_loss"] == -80.0
        # profit factor = 225 / 80 = 2.8125 -> 2.81
        assert data["profit_factor"] == 2.81
        # expectancy = 0.6*75 + 0.4*(-80)
        #   = 45 + (-32) = 13.0
        assert data["expectancy"] == 13.0

        # APPT = 145 / 5 = 29.0
        assert data["appt"] == 29.0
        # P/L Ratio = 75 / 80 = 0.9375 -> 0.94
        assert data["pl_ratio"] == 0.94
        # Per-share: all trades have total_quantity=1
        # win_per_share_avg = (100+50+75)/3 = 75.0
        assert data["win_per_share_avg"] == 75.0
        # win_per_share_high = 100.0
        assert data["win_per_share_high"] == 100.0
        # loss_per_share_avg = -80/1 = -80.0
        assert data["loss_per_share_avg"] == -80.0
        # loss_per_share_high = -80.0
        assert data["loss_per_share_high"] == -80.0

    def test_summary_excludes_deleted(
        self, app, client, auth_headers
    ):
        """Deleted trades are excluded from summary."""
        user_id = _get_user_id(app)
        _insert_trade(
            app, user_id, net_pnl=100.0, status="closed"
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=500.0,
            status="deleted",
        )

        resp = client.get(
            "/api/analytics/summary",
            headers=auth_headers,
        )
        data = resp.json
        assert data["total_trades"] == 1
        assert data["total_net_pnl"] == 100.0

    def test_summary_filter_by_symbol(
        self, app, client, auth_headers
    ):
        """Summary can be filtered by symbol."""
        user_id = _get_user_id(app)
        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            symbol="MES",
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=200.0,
            symbol="MNQ",
        )

        resp = client.get(
            "/api/analytics/summary?symbol=MES",
            headers=auth_headers,
        )
        data = resp.json
        assert data["total_trades"] == 1
        assert data["total_net_pnl"] == 100.0


class TestEquityCurve:
    """Tests for GET /api/analytics/equity-curve."""

    def test_equity_curve(
        self, app, client, auth_headers
    ):
        """Equity curve shows daily cumulative P&L."""
        user_id = _get_user_id(app)

        # Three trades on day 1, one trade on day 2
        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            exit_time=datetime(2025, 1, 15, 11, 0, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-30.0,
            exit_time=datetime(2025, 1, 15, 12, 0, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=50.0,
            exit_time=datetime(2025, 1, 16, 10, 0, 0),
        )

        resp = client.get(
            "/api/analytics/equity-curve",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        # Two days of data
        assert len(data) == 2
        # Day 1: 100 + (-30) = 70 daily, 70 cumulative
        assert data[0]["date"] == "2025-01-15"
        assert data[0]["daily_pnl"] == 70.0
        assert data[0]["cumulative_pnl"] == 70.0
        assert data[0]["trade_count"] == 2
        assert data[0]["winners"] == 1
        assert data[0]["win_rate"] == 50.0
        assert data[0]["appt"] == 35.0
        # Day 2: 50 daily, 120 cumulative
        assert data[1]["date"] == "2025-01-16"
        assert data[1]["daily_pnl"] == 50.0
        assert data[1]["cumulative_pnl"] == 120.0
        assert data[1]["trade_count"] == 1
        assert data[1]["winners"] == 1
        assert data[1]["win_rate"] == 100.0

    def test_equity_curve_empty(
        self, client, auth_headers
    ):
        """Equity curve returns empty list."""
        resp = client.get(
            "/api/analytics/equity-curve",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json == []


class TestDrawdown:
    """Tests for GET /api/analytics/drawdown."""

    def test_drawdown(self, app, client, auth_headers):
        """Drawdown shows peak-to-trough decline."""
        user_id = _get_user_id(app)

        # Day 1: +100, Day 2: -30, Day 3: +50
        # Equity: 100, 70, 120
        # Peak:   100, 100, 120
        # DD:     0, -30, 0
        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            exit_time=datetime(2025, 1, 15, 11, 0, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-30.0,
            exit_time=datetime(2025, 1, 16, 12, 0, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=50.0,
            exit_time=datetime(2025, 1, 17, 13, 0, 0),
        )

        resp = client.get(
            "/api/analytics/drawdown",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert len(data) == 3
        assert data[0]["drawdown"] == 0.0
        assert data[1]["drawdown"] == -30.0
        assert data[1]["drawdown_pct"] == -30.0
        assert data[2]["drawdown"] == 0.0


class TestCalendar:
    """Tests for GET /api/analytics/calendar."""

    def test_calendar_groups_by_date(
        self, app, client, auth_headers
    ):
        """Calendar groups trades by exit date."""
        user_id = _get_user_id(app)

        # Two trades on same day, one on different day
        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            exit_time=datetime(2025, 1, 15, 10, 0, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-50.0,
            exit_time=datetime(2025, 1, 15, 14, 0, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=200.0,
            exit_time=datetime(2025, 1, 16, 10, 0, 0),
        )

        resp = client.get(
            "/api/analytics/calendar",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert len(data) == 2
        day1 = data[0]
        assert day1["date"] == "2025-01-15"
        assert day1["net_pnl"] == 50.0
        assert day1["trade_count"] == 2

        day2 = data[1]
        assert day2["date"] == "2025-01-16"
        assert day2["net_pnl"] == 200.0
        assert day2["trade_count"] == 1


class TestDistribution:
    """Tests for GET /api/analytics/distribution."""

    def test_distribution_buckets(
        self, app, client, auth_headers
    ):
        """Distribution groups P&L into buckets."""
        user_id = _get_user_id(app)

        # net_pnl values: 120, 80, -30, -90
        # With bucket_size=100:
        #   120 -> floor(120/100)*100 = 100
        #   80  -> floor(80/100)*100  = 0
        #   -30 -> floor(-30/100)*100 = -100
        #   -90 -> floor(-90/100)*100 = -100
        base = datetime(2025, 1, 15, 10, 0, 0)
        _insert_trade(
            app,
            user_id,
            net_pnl=120.0,
            exit_time=base + timedelta(hours=1),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=80.0,
            exit_time=base + timedelta(hours=2),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-30.0,
            exit_time=base + timedelta(hours=3),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-90.0,
            exit_time=base + timedelta(hours=4),
        )

        resp = client.get(
            "/api/analytics/distribution"
            "?bucket_size=100",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        # Expect 3 buckets: -100 (2), 0 (1), 100 (1)
        assert len(data) == 3
        buckets = {d["bucket"]: d["count"] for d in data}
        assert buckets[-100] == 2
        assert buckets[0] == 1
        assert buckets[100] == 1


class TestTimeOfDay:
    """Tests for GET /api/analytics/time-of-day."""

    def test_time_of_day(
        self, app, client, auth_headers
    ):
        """Time-of-day groups trades by entry hour."""
        user_id = _get_user_id(app)

        # Two trades at hour 9, one at hour 14
        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            entry_time=datetime(2025, 1, 15, 9, 15, 0),
            exit_time=datetime(2025, 1, 15, 9, 45, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-50.0,
            entry_time=datetime(2025, 1, 15, 9, 30, 0),
            exit_time=datetime(2025, 1, 15, 10, 0, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=200.0,
            entry_time=datetime(
                2025, 1, 15, 14, 0, 0
            ),
            exit_time=datetime(
                2025, 1, 15, 14, 30, 0
            ),
        )

        resp = client.get(
            "/api/analytics/time-of-day",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert len(data) == 2
        h9 = next(d for d in data if d["hour"] == 9)
        assert h9["trade_count"] == 2
        assert h9["net_pnl"] == 50.0
        assert h9["win_rate"] == 50.0

        h14 = next(d for d in data if d["hour"] == 14)
        assert h14["trade_count"] == 1
        assert h14["win_rate"] == 100.0


class TestByTag:
    """Tests for GET /api/analytics/by-tag."""

    def test_by_tag(self, app, client, auth_headers):
        """By-tag groups metrics per tag."""
        user_id = _get_user_id(app)

        # Create two tags
        with app.app_context():
            tag1_id = mongo.db.tags.insert_one(
                {
                    "user_id": user_id,
                    "name": "Momentum",
                    "color": "#FF0000",
                }
            ).inserted_id
            tag2_id = mongo.db.tags.insert_one(
                {
                    "user_id": user_id,
                    "name": "Reversal",
                    "color": "#00FF00",
                }
            ).inserted_id

        # Trade with tag1
        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            tag_ids=[tag1_id],
        )
        # Trade with tag1 and tag2
        _insert_trade(
            app,
            user_id,
            net_pnl=-50.0,
            tag_ids=[tag1_id, tag2_id],
        )
        # Trade with tag2
        _insert_trade(
            app,
            user_id,
            net_pnl=80.0,
            tag_ids=[tag2_id],
        )

        resp = client.get(
            "/api/analytics/by-tag",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert len(data) == 2

        # Find by tag name
        momentum = next(
            d for d in data if d["tag_name"] == "Momentum"
        )
        reversal = next(
            d for d in data if d["tag_name"] == "Reversal"
        )

        assert momentum["trade_count"] == 2
        assert momentum["net_pnl"] == 50.0
        assert momentum["win_rate"] == 50.0

        assert reversal["trade_count"] == 2
        assert reversal["net_pnl"] == 30.0
        assert reversal["win_rate"] == 50.0

    def test_by_tag_no_tags(
        self, client, auth_headers
    ):
        """By-tag returns empty when no tagged trades."""
        resp = client.get(
            "/api/analytics/by-tag",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json == []


class TestAnalyticsAuth:
    """Test that analytics endpoints require auth."""

    def test_summary_requires_auth(self, client):
        """Summary endpoint requires JWT."""
        resp = client.get("/api/analytics/summary")
        assert resp.status_code == 401

    def test_equity_curve_requires_auth(self, client):
        """Equity curve endpoint requires JWT."""
        resp = client.get("/api/analytics/equity-curve")
        assert resp.status_code == 401
