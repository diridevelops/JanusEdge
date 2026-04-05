"""Market data API routes."""

from pathlib import Path

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.market_data import market_data_bp
from app.market_data.config import (
    MARKET_DATA_ACCEPTED_EXTENSIONS,
)
from app.market_data.service import MarketDataService
from app.market_data.symbol_mapper import (
    get_effective_market_data_mappings,
)
from app.repositories.user_repo import UserRepository
from app.tick_data.service import TickDataService
from app.utils.errors import ValidationError
from app.utils import upload_limits

market_data_service = MarketDataService()
tick_data_service = TickDataService()
user_repo = UserRepository()


def _market_data_file_too_large_message() -> str:
    """Return the current market-data oversize error message."""

    return (
        "Tick-data files must be "
        f"{upload_limits.format_upload_limit(upload_limits.MARKET_DATA_MAX_FILE_SIZE)} "
        "or smaller."
    )


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


@market_data_bp.route("/saved-days", methods=["GET"])
@jwt_required()
def get_saved_days():
    """Return saved market-data day summaries for the market-data page."""

    saved_days = market_data_service.list_saved_days(
        user_id=get_jwt_identity()
    )
    return jsonify({"saved_days": saved_days}), 200


@market_data_bp.route("/tick-imports/preview", methods=["POST"])
@jwt_required()
def preview_tick_import():
    """Start a background preview for a NinjaTrader tick-data text file."""

    if "file" not in request.files:
        raise ValidationError("No file provided.")

    file = request.files["file"]
    if file.filename == "":
        raise ValidationError("No file selected.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in MARKET_DATA_ACCEPTED_EXTENSIONS:
        raise ValidationError(
            "Only NinjaTrader text exports are supported."
        )

    upload_limits.enforce_upload_file_size(
        file,
        max_size_bytes=upload_limits.MARKET_DATA_MAX_FILE_SIZE,
        error_message=_market_data_file_too_large_message(),
    )

    batch = tick_data_service.start_ninjatrader_preview(
        user_id=get_jwt_identity(),
        file_name=file.filename,
        file_stream=file.stream,
    )
    return jsonify(batch), 202


@market_data_bp.route(
    "/tick-imports/preview/<batch_id>",
    methods=["GET"],
)
@jwt_required()
def get_tick_import_preview(batch_id: str):
    """Return the current progress for one tick-data preview batch."""

    batch = tick_data_service.get_preview_batch(
        user_id=get_jwt_identity(),
        batch_id=batch_id,
    )
    return jsonify(batch), 200


@market_data_bp.route("/tick-imports", methods=["POST"])
@jwt_required()
def create_tick_import():
    """Start a background NinjaTrader tick-data import."""

    if "file" not in request.files:
        raise ValidationError("No file provided.")

    file = request.files["file"]
    if file.filename == "":
        raise ValidationError("No file selected.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in MARKET_DATA_ACCEPTED_EXTENSIONS:
        raise ValidationError(
            "Only NinjaTrader text exports are supported."
        )

    upload_limits.enforce_upload_file_size(
        file,
        max_size_bytes=upload_limits.MARKET_DATA_MAX_FILE_SIZE,
        error_message=_market_data_file_too_large_message(),
    )

    user = user_repo.find_by_id(get_jwt_identity())
    batch = tick_data_service.start_ninjatrader_import(
        user_id=get_jwt_identity(),
        file_name=file.filename,
        file_stream=file.stream,
        symbol=request.form.get("symbol"),
        raw_symbol=request.form.get("raw_symbol"),
        market_data_mappings=get_effective_market_data_mappings(
            user.get("market_data_mappings") if user else None
        ),
    )
    return jsonify(batch), 202


@market_data_bp.route(
    "/tick-imports/<batch_id>",
    methods=["GET"],
)
@jwt_required()
def get_tick_import(batch_id: str):
    """Return the current progress for one tick-data import batch."""

    batch = tick_data_service.get_import_batch(
        user_id=get_jwt_identity(),
        batch_id=batch_id,
    )
    return jsonify(batch), 200
