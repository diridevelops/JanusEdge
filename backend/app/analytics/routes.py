"""Analytics API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.analytics import analytics_bp
from app.analytics.monte_carlo import MonteCarloParams
from app.analytics.service import AnalyticsService

analytics_service = AnalyticsService()

DEFAULT_STARTING_EQUITY = 10_000.0
DEFAULT_WIN_RATE = 50.0
DEFAULT_WIN_LOSS_RATIO = 2.0
DEFAULT_NUM_TRADES = 500
DEFAULT_RISK_FIXED = 200.0
DEFAULT_RISK_PCT = 1.0
DEFAULT_MIN_RISK = 50.0


def _parse_filters() -> dict:
    """
    Parse common filter query parameters.

    Extracts account, symbol, side, tag, date_from,
    and date_to from request args.

    Returns:
        Dict of filter parameters.
    """
    return {
        "account": request.args.get("account"),
        "symbol": request.args.get("symbol"),
        "side": request.args.get("side"),
        "tag": request.args.get("tag"),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
        "timezone": request.args.get("timezone"),
    }


def _body_value(body: dict, *keys: str, default=None):
    """Return the first present body value across key variants."""
    for key in keys:
        if key in body:
            return body[key]
    return default


def _parse_float(
    value,
    field_name: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Parse and validate a float request field."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc

    if minimum is not None and parsed < minimum:
        raise ValueError(
            f"{field_name} must be at least {minimum}"
        )
    if maximum is not None and parsed > maximum:
        raise ValueError(
            f"{field_name} must be at most {maximum}"
        )
    return parsed


def _parse_int(
    value,
    field_name: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Parse and validate an integer request field."""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc

    if minimum is not None and parsed < minimum:
        raise ValueError(
            f"{field_name} must be at least {minimum}"
        )
    if maximum is not None and parsed > maximum:
        raise ValueError(
            f"{field_name} must be at most {maximum}"
        )
    return parsed


def _parse_monte_carlo_params(body: dict) -> MonteCarloParams:
    """Parse Monte Carlo request JSON into validated params."""
    mode = str(
        _body_value(body, "mode", default="parametric")
    ).strip().lower()
    if mode not in {"bootstrap", "parametric"}:
        raise ValueError(
            "mode must be 'bootstrap' or 'parametric'"
        )

    risk_mode = str(
        _body_value(body, "riskMode", "risk_mode", default="percent")
    ).strip().lower()
    if risk_mode not in {"fixed", "percent"}:
        raise ValueError(
            "riskMode must be 'fixed' or 'percent'"
        )

    return MonteCarloParams(
        mode=mode,
        starting_equity=_parse_float(
            _body_value(
                body,
                "startingEquity",
                "starting_equity",
                default=DEFAULT_STARTING_EQUITY,
            ),
            "startingEquity",
            minimum=0.01,
        ),
        win_rate=_parse_float(
            _body_value(
                body,
                "winRate",
                "win_rate",
                default=DEFAULT_WIN_RATE,
            ),
            "winRate",
            minimum=0.0,
            maximum=100.0,
        ),
        win_loss_ratio=_parse_float(
            _body_value(
                body,
                "winLossRatio",
                "win_loss_ratio",
                default=DEFAULT_WIN_LOSS_RATIO,
            ),
            "winLossRatio",
            minimum=0.0,
        ),
        risk_fixed=_parse_float(
            _body_value(
                body,
                "riskFixed",
                "risk_fixed",
                default=DEFAULT_RISK_FIXED,
            ),
            "riskFixed",
            minimum=0.0,
        ),
        risk_pct=_parse_float(
            _body_value(
                body,
                "riskPct",
                "risk_pct",
                default=DEFAULT_RISK_PCT,
            ),
            "riskPct",
            minimum=0.0,
        ),
        min_risk=_parse_float(
            _body_value(
                body,
                "minRisk",
                "min_risk",
                default=DEFAULT_MIN_RISK,
            ),
            "minRisk",
            minimum=0.0,
        ),
        risk_mode=risk_mode,
        seed=_parse_int(
            _body_value(body, "seed", default=42),
            "seed",
        ),
        num_trades=_parse_int(
            _body_value(
                body,
                "numTrades",
                "num_trades",
                default=DEFAULT_NUM_TRADES,
            ),
            "numTrades",
            minimum=10,
            maximum=1000,
        ),
    )


@analytics_bp.route("/summary", methods=["GET"])
@jwt_required()
def get_summary():
    """
    Get summary metrics for closed trades.

    Query parameters:
        account: Filter by trade account ID.
        symbol: Filter by symbol.
        side: Filter by side (Long/Short).
        tag: Filter by tag ID.
        date_from: ISO date string for range start.
        date_to: ISO date string for range end.

    Returns:
        JSON with summary metrics.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    summary = analytics_service.get_summary(
        user_id, filters
    )
    return jsonify(summary), 200


@analytics_bp.route("/trade-pnls", methods=["GET"])
@jwt_required()
def get_trade_pnls():
    """
    Get per-trade net P&L values for bootstrap resampling.

    Returns:
        JSON array of {net_pnl} dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_trade_pnls(
        user_id, filters
    )
    return jsonify(data), 200


@analytics_bp.route("/equity-curve", methods=["GET"])
@jwt_required()
def get_equity_curve():
    """
    Get equity curve data points.

    Returns:
        JSON array of {time, net_pnl,
        cumulative_pnl, symbol} dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_equity_curve(
        user_id, filters
    )
    return jsonify(data), 200


@analytics_bp.route("/drawdown", methods=["GET"])
@jwt_required()
def get_drawdown():
    """
    Get drawdown series.

    Returns:
        JSON array of {time, cumulative_pnl,
        drawdown, drawdown_pct} dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_drawdown(
        user_id, filters
    )
    return jsonify(data), 200


@analytics_bp.route("/calendar", methods=["GET"])
@jwt_required()
def get_calendar():
    """
    Get calendar heatmap data (daily P&L).

    Returns:
        JSON array of {date, net_pnl, gross_pnl,
        trade_count} dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_calendar(
        user_id, filters
    )
    return jsonify(data), 200


@analytics_bp.route("/distribution", methods=["GET"])
@jwt_required()
def get_distribution():
    """
    Get P&L distribution histogram.

    Query parameters:
        bucket_size: Width of histogram buckets
            (default 50).

    Returns:
        JSON array of {bucket, count} dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    bucket_size = float(
        request.args.get("bucket_size", 50)
    )
    data = analytics_service.get_distribution(
        user_id, filters, bucket_size
    )
    return jsonify(data), 200


@analytics_bp.route("/time-of-day", methods=["GET"])
@jwt_required()
def get_time_of_day():
    """
    Get performance by hour of day.

    Returns:
        JSON array of {hour, trade_count, net_pnl,
        avg_pnl, win_rate} dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_time_of_day(
        user_id, filters
    )
    return jsonify(data), 200


@analytics_bp.route("/by-tag", methods=["GET"])
@jwt_required()
def get_by_tag():
    """
    Get metrics grouped by tag.

    Returns:
        JSON array of per-tag metric dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_by_tag(
        user_id, filters
    )
    return jsonify(data), 200


@analytics_bp.route(
    "/appt-by-day-of-week", methods=["GET"]
)
@jwt_required()
def get_appt_by_day_of_week():
    """
    Get APPT grouped by day of week.

    Returns:
        JSON array of {day_of_week, appt,
        trade_count, net_pnl} dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_appt_by_day_of_week(
        user_id, filters
    )
    return jsonify(data), 200


@analytics_bp.route(
    "/appt-by-timeframe", methods=["GET"]
)
@jwt_required()
def get_appt_by_timeframe():
    """
    Get APPT grouped by 15-minute entry buckets.

    Returns:
        JSON array of {timespan_start, appt,
        trade_count, net_pnl} dicts.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_appt_by_timeframe(
        user_id, filters
    )
    return jsonify(data), 200


@analytics_bp.route("/evolution", methods=["GET"])
@jwt_required()
def get_evolution():
    """
    Get running and rolling performance metrics
    after each trade.

    Query parameters:
        window: Rolling window length (default 50).
        min_side_count: Minimum wins/losses in window
            for stable P/L ratio (default 2).

    Returns:
        JSON array of per-trade evolution points.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    window = int(request.args.get("window", 50))
    min_side_count = int(
        request.args.get("min_side_count", 2)
    )
    data = analytics_service.get_evolution(
        user_id,
        filters,
        window=window,
        min_side_count=min_side_count,
    )
    return jsonify(data), 200


@analytics_bp.route("/monte-carlo", methods=["POST"])
@jwt_required()
def get_monte_carlo():
    """Run Monte Carlo simulations for the analytics dashboard."""
    body = request.get_json(silent=True) or {}
    try:
        params = _parse_monte_carlo_params(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    user_id = get_jwt_identity()
    filters = _parse_filters()
    data = analytics_service.get_monte_carlo(
        user_id,
        params,
        filters,
    )
    return jsonify(data), 200
