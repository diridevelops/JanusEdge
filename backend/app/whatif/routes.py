"""What-if API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.whatif import whatif_bp
from app.whatif.service import WhatIfService

whatif_service = WhatIfService()


def _parse_filters() -> dict:
    """
    Parse common filter query parameters.

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
    }


@whatif_bp.route("/stop-analysis", methods=["GET"])
@jwt_required()
def stop_analysis():
    """
    Get R-normalized stop overshoot statistics.

    Requires a symbol filter. Returns mean, median,
    percentiles, IQR, bootstrap CI, and per-trade
    detail for wicked-out trades.

    Query parameters:
        symbol: Required instrument filter.
        account: Optional trade account ID.
        side: Optional side filter (Long/Short).
        tag: Optional tag filter.
        date_from: ISO date string for range start.
        date_to: ISO date string for range end.

    Returns:
        JSON with stop analysis statistics.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    result = whatif_service.get_stop_analysis(
        user_id, filters
    )
    return jsonify(result), 200


@whatif_bp.route(
    "/wicked-out-trades", methods=["GET"]
)
@jwt_required()
def wicked_out_trades():
    """
    List wicked-out trades with tick-data availability.

    Returns trade summaries with has_tick_data flag.

    Query parameters:
        symbol: Optional instrument filter.
        account: Optional trade account ID.
        side: Optional side filter.
        tag: Optional tag filter.
        date_from: ISO date string for range start.
        date_to: ISO date string for range end.

    Returns:
        JSON with list of wicked-out trade summaries.
    """
    user_id = get_jwt_identity()
    filters = _parse_filters()
    result = whatif_service.get_wicked_out_trades(
        user_id, filters
    )
    return jsonify(result), 200


@whatif_bp.route("/simulate", methods=["POST"])
@jwt_required()
def simulate():
    """
    Run what-if stop widening simulation.

    Accepts r_widening and optional filters. Replays
    either 1-minute OHLC candles or raw ticks for losing trades with target prices
    to simulate wider stop outcomes.

    JSON body:
        r_widening: float — stop widening factor in R.
        replay_mode: optional string — 'ohlc' or 'tick'.

    Query parameters:
        symbol: Optional instrument filter.
        account: Optional trade account ID.
        side: Optional side filter.
        tag: Optional tag filter.
        date_from: ISO date string for range start.
        date_to: ISO date string for range end.

    Returns:
        JSON with original/what-if metrics comparison.
    """
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}
    r_widening = body.get("r_widening")
    replay_mode = str(
        body.get("replay_mode", "ohlc")
    ).strip().lower()

    if r_widening is None:
        return (
            jsonify({"error": "r_widening is required"}),
            400,
        )

    try:
        r_widening = float(r_widening)
    except (TypeError, ValueError):
        return (
            jsonify(
                {"error": "r_widening must be a number"}
            ),
            400,
        )

    if r_widening < 0 or r_widening > 10:
        return (
            jsonify(
                {
                    "error": "r_widening must be "
                    "between 0 and 10"
                }
            ),
            400,
        )

    if replay_mode not in {"ohlc", "tick"}:
        return (
            jsonify(
                {
                    "error": "replay_mode must be "
                    "'ohlc' or 'tick'"
                }
            ),
            400,
        )

    filters = _parse_filters()
    result = whatif_service.simulate(
        user_id,
        r_widening,
        replay_mode=replay_mode,
        filters=filters,
    )
    return jsonify(result), 200
