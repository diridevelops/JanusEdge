"""Market data API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.market_data import market_data_bp
from app.market_data.service import MarketDataService
from app.utils.errors import ValidationError

market_data_service = MarketDataService()


@market_data_bp.route("/ohlc", methods=["GET"])
@jwt_required()
def get_ohlc():
    """
    Get OHLC candlestick data.

    Query params:
        symbol: Normalized symbol (required).
        interval: '1m', '5m', '15m', '1h', '1d'.
        start: Start date (ISO).
        end: End date (ISO).
        raw_symbol: Original platform symbol.

    Returns: {ohlc_data[]}
    """
    symbol = request.args.get("symbol")
    if not symbol:
        raise ValidationError("Symbol is required.")

    interval = request.args.get("interval", "5m")
    start = request.args.get("start")
    end = request.args.get("end")
    raw_symbol = request.args.get("raw_symbol")
    force_refresh = request.args.get(
        "force_refresh", "false"
    ).lower() in ("1", "true", "yes")
    user_id = get_jwt_identity()

    ohlc = market_data_service.get_ohlc(
        user_id=user_id,
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        raw_symbol=raw_symbol,
        force_refresh=force_refresh,
    )
    return jsonify({"ohlc_data": ohlc}), 200
