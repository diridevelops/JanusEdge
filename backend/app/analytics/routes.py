"""Analytics API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.analytics import analytics_bp
from app.analytics.service import AnalyticsService

analytics_service = AnalyticsService()


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
