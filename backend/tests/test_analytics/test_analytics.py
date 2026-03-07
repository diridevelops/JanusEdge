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
    total_quantity=1,
    initial_risk=0.0,
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
        "total_quantity": total_quantity,
        "max_quantity": total_quantity,
        "avg_entry_price": 5000.0,
        "avg_exit_price": 5000.0
        + (net_pnl + fee) / 5.0,
        "gross_pnl": gross_pnl,
        "fee": fee,
        "fee_source": "csv",
        "net_pnl": net_pnl,
        "initial_risk": initial_risk,
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
        assert data["expectancy_r"] is None
        assert data["win_per_share_avg"] == 0.0
        assert data["loss_per_share_avg"] == 0.0

    def test_summary_basic(
        self, app, client, auth_headers
    ):
        """Summary computes correct metrics."""
        user_id = _get_user_id(app)

        # Insert 5 trades: 3 winners, 1 loser, 1 BE
        # Breakeven = gross_pnl == 0 (trade itself was flat)
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
            net_pnl=-2.0,
            gross_pnl=0.0,
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
        assert data["total_net_pnl"] == 143.0
        assert data["total_fees"] == 10.0

        # avg winner = (100+50+75)/3 = 75.0
        assert data["avg_winner"] == 75.0
        # avg loser = -80/1 = -80.0 (breakeven excluded)
        assert data["avg_loser"] == -80.0
        # largest win = 100
        assert data["largest_win"] == 100.0
        # largest loss = -80
        assert data["largest_loss"] == -80.0
        # profit factor = 225 / 82 = 2.7439 -> 2.74
        # fee-only breakeven trades are included in PF denominator
        assert data["profit_factor"] == 2.74
        # expectancy = 0.6*75 + 0.4*(-80) = 45-32 = 13.0
        assert data["expectancy"] == 13.0

        # APPT = 143 / 5 = 28.6
        assert data["appt"] == 28.6
        # P/L Ratio = 75 / 80 = 0.9375 -> 0.94
        assert data["pl_ratio"] == 0.94
        # Per-share: all trades have total_quantity=1
        # win_per_share_avg = (100+50+75)/3 = 75.0
        assert data["win_per_share_avg"] == 75.0
        # win_per_share_high = 100.0
        assert data["win_per_share_high"] == 100.0
        # loss_per_share_avg = -80/1 = -80.0 (breakeven excluded)
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

    def test_summary_pl_ratio_uses_per_trade_values(
        self, app, client, auth_headers
    ):
        """P/L ratio uses avg win and avg loss per trade."""
        user_id = _get_user_id(app)
        base = datetime(2025, 1, 18, 12, 0, 0)

        _insert_trade(
            app,
            user_id,
            net_pnl=200.0,
            fee=0.0,
            total_quantity=4,
            exit_time=base,
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=50.0,
            fee=0.0,
            total_quantity=1,
            exit_time=base + timedelta(hours=1),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-90.0,
            fee=0.0,
            total_quantity=3,
            exit_time=base + timedelta(hours=2),
        )

        resp = client.get(
            "/api/analytics/summary",
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json
        # Avg winner = (200 + 50) / 2 = 125
        # Avg loser = -90
        # P/L ratio = 125 / 90 = 1.388... -> 1.39
        assert data["pl_ratio"] == 1.39

    def test_summary_expectancy_r_uses_defined_r_only(
        self, app, client, auth_headers
    ):
        """Expectancy (R) includes only trades with initial risk > 0."""
        user_id = _get_user_id(app)
        base = datetime(2025, 1, 20, 12, 0, 0)

        _insert_trade(
            app,
            user_id,
            net_pnl=200.0,
            initial_risk=100.0,
            exit_time=base,
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-50.0,
            initial_risk=100.0,
            exit_time=base + timedelta(hours=1),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=120.0,
            initial_risk=0.0,
            exit_time=base + timedelta(hours=2),
        )

        resp = client.get(
            "/api/analytics/summary",
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json
        # Defined-R trades: +2.0R and -0.5R
        # win_rate=0.5, avg_win_r=2.0, avg_loss_r=0.5
        # expectancy_r=0.5*2.0 - 0.5*0.5 = 0.75
        assert data["expectancy_r"] == 0.75

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


class TestApptByDayOfWeek:
    """Tests for GET /api/analytics/appt-by-day-of-week."""

    def test_appt_by_day_of_week(
        self, app, client, auth_headers
    ):
        """Returns Monday-Sunday buckets with APPT values."""
        user_id = _get_user_id(app)

        # Monday (2025-01-13) two trades: +100, -50 => APPT 25
        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            entry_time=datetime(2025, 1, 13, 9, 5, 0),
            exit_time=datetime(2025, 1, 13, 9, 35, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-50.0,
            entry_time=datetime(2025, 1, 13, 10, 5, 0),
            exit_time=datetime(2025, 1, 13, 10, 35, 0),
        )

        # Tuesday one trade: +40 => APPT 40
        _insert_trade(
            app,
            user_id,
            net_pnl=40.0,
            entry_time=datetime(2025, 1, 14, 11, 0, 0),
            exit_time=datetime(2025, 1, 14, 11, 30, 0),
        )

        resp = client.get(
            "/api/analytics/appt-by-day-of-week",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert len(data) == 7
        assert data[0]["day_of_week"] == "Monday"
        assert data[1]["day_of_week"] == "Tuesday"
        assert data[6]["day_of_week"] == "Sunday"

        monday = data[0]
        assert monday["trade_count"] == 2
        assert monday["net_pnl"] == 50.0
        assert monday["appt"] == 25.0

        tuesday = data[1]
        assert tuesday["trade_count"] == 1
        assert tuesday["net_pnl"] == 40.0
        assert tuesday["appt"] == 40.0


class TestApptByTimeframe:
    """Tests for GET /api/analytics/appt-by-timeframe."""

    def test_appt_by_timeframe(
        self, app, client, auth_headers
    ):
        """Groups APPT by 15-minute entry buckets."""
        user_id = _get_user_id(app)

        # 09:00 bucket (09:00-09:14:59): +90, -30 => APPT 30
        _insert_trade(
            app,
            user_id,
            net_pnl=90.0,
            entry_time=datetime(2025, 1, 15, 9, 2, 0),
            exit_time=datetime(2025, 1, 15, 9, 32, 0),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-30.0,
            entry_time=datetime(2025, 1, 15, 9, 10, 0),
            exit_time=datetime(2025, 1, 15, 9, 40, 0),
        )

        # 09:15 bucket: +45 => APPT 45
        _insert_trade(
            app,
            user_id,
            net_pnl=45.0,
            entry_time=datetime(2025, 1, 15, 9, 18, 0),
            exit_time=datetime(2025, 1, 15, 9, 48, 0),
        )

        resp = client.get(
            "/api/analytics/appt-by-timeframe",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert len(data) == 2
        assert data[0]["timespan_start"] == "09:00"
        assert data[0]["trade_count"] == 2
        assert data[0]["net_pnl"] == 60.0
        assert data[0]["appt"] == 30.0

        assert data[1]["timespan_start"] == "09:15"
        assert data[1]["trade_count"] == 1
        assert data[1]["net_pnl"] == 45.0
        assert data[1]["appt"] == 45.0


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


class TestEvolution:
    """Tests for GET /api/analytics/evolution."""

    def test_evolution_empty(
        self, client, auth_headers
    ):
        """Returns empty list when no trades exist."""
        resp = client.get(
            "/api/analytics/evolution",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json == []

    def test_evolution_running_and_rolling_metrics(
        self, app, client, auth_headers
    ):
        """Computes running/rolling metrics by trade index."""
        user_id = _get_user_id(app)
        base = datetime(2025, 2, 1, 10, 0, 0)

        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            initial_risk=50.0,
            exit_time=base,
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-50.0,
            initial_risk=50.0,
            exit_time=base + timedelta(minutes=10),
        )
        # Undefined R (initial_risk=0) still contributes to money metrics
        _insert_trade(
            app,
            user_id,
            net_pnl=25.0,
            initial_risk=0.0,
            exit_time=base + timedelta(minutes=20),
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=40.0,
            initial_risk=20.0,
            exit_time=base + timedelta(minutes=30),
        )

        resp = client.get(
            "/api/analytics/evolution?window=3&min_side_count=1",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert len(data) == 4

        first = data[0]
        assert first["trade_index"] == 1
        assert first["r_multiple"] == 2.0
        assert first["included_r_count"] == 1
        assert first["running_mean_r"] == 2.0
        assert first["cum_r"] == 2.0
        assert first["cum_net_pnl"] == 100.0

        second = data[1]
        assert second["r_multiple"] == -1.0
        # running mean R = (2 + -1) / 2 = 0.5
        assert second["running_mean_r"] == 0.5
        assert second["cum_r"] == 1.0
        # rolling ratio in first 2 trades: avg win 100 / |avg loss -50| = 2
        assert second["rolling_pl_ratio_trade"] == 2.0

        third = data[2]
        assert third["r_multiple"] is None
        # Undefined R excluded from R metrics
        assert third["included_r_count"] == 2
        assert third["running_mean_r"] == 0.5
        # Money metrics still include all trades
        assert third["cum_net_pnl"] == 75.0
        assert third["appt_running"] == 25.0

        fourth = data[3]
        assert fourth["r_multiple"] == 2.0
        # Running mean R = (2 + -1 + 2) / 3 = 1.0
        assert fourth["running_mean_r"] == 1.0
        # Rolling R over last 3 defined-R trades = (2 + -1 + 2) / 3 = 1
        assert fourth["rolling_mean_r"] == 1.0

    def test_evolution_pl_ratio_guardrail(
        self, app, client, auth_headers
    ):
        """Hides rolling trade P/L ratio until both sides meet minimum count."""
        user_id = _get_user_id(app)
        base = datetime(2025, 2, 3, 10, 0, 0)

        _insert_trade(
            app,
            user_id,
            net_pnl=100.0,
            initial_risk=50.0,
            exit_time=base,
        )
        _insert_trade(
            app,
            user_id,
            net_pnl=-40.0,
            initial_risk=40.0,
            exit_time=base + timedelta(minutes=5),
        )

        resp = client.get(
            "/api/analytics/evolution?window=10&min_side_count=2",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json

        assert len(data) == 2
        # One win + one loss is below min_side_count=2
        assert data[-1]["rolling_pl_ratio_trade"] is None
        assert data[-1]["rolling_pl_ratio_stable"] is False
