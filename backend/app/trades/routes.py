"""Trade API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)
from marshmallow import (
    ValidationError as MarshmallowError,
)

from app.trades import trades_bp
from app.trades.schemas import (
    ManualTradeSchema,
    UpdateTradeSchema,
)
from app.trades.service import TradeService
from app.utils.errors import ValidationError

trade_service = TradeService()
manual_trade_schema = ManualTradeSchema()
update_trade_schema = UpdateTradeSchema()


@trades_bp.route("", methods=["GET"])
@jwt_required()
def list_trades():
    """
    List trades with filters and pagination.

    Query params: account, symbol, side, tag,
        date_from, date_to, page, per_page,
        sort_by, sort_dir
    """
    user_id = get_jwt_identity()
    result = trade_service.list_trades(
        user_id=user_id,
        account=request.args.get("account"),
        symbol=request.args.get("symbol"),
        side=request.args.get("side"),
        tag=request.args.get("tag"),
        date_from=request.args.get("date_from"),
        date_to=request.args.get("date_to"),
        page=int(request.args.get("page", 1)),
        per_page=int(request.args.get("per_page", 25)),
        sort_by=request.args.get(
            "sort_by", "entry_time"
        ),
        sort_dir=request.args.get("sort_dir", "desc"),
    )
    return jsonify(result), 200


@trades_bp.route("/<trade_id>", methods=["GET"])
@jwt_required()
def get_trade(trade_id):
    """
    Get trade detail with executions.

    Returns: {trade, executions[]}
    """
    user_id = get_jwt_identity()
    result = trade_service.get_trade(user_id, trade_id)
    return jsonify(result), 200


@trades_bp.route("", methods=["POST"])
@jwt_required()
def create_trade():
    """
    Create a manual trade.

    Expects JSON: {symbol, side, total_quantity,
        entry_price, exit_price, entry_time, exit_time,
        fee?, account?, tags?, notes?}
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = manual_trade_schema.load(data)
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    trade = trade_service.create_manual_trade(
        user_id, validated
    )
    return jsonify({"trade": trade}), 201


@trades_bp.route("/<trade_id>", methods=["PUT"])
@jwt_required()
def update_trade(trade_id):
    """
    Update trade (fees, notes, tags, strategy).

    Expects JSON with updatable fields.
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = update_trade_schema.load(data)
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    trade = trade_service.update_trade(
        user_id, trade_id, validated
    )
    return jsonify({"trade": trade}), 200


@trades_bp.route(
    "/<trade_id>/detect-wish-stop", methods=["POST"]
)
@jwt_required()
def detect_wish_stop(trade_id):
    """Detect a suggested wishful stop from stored OHLC bars."""
    user_id = get_jwt_identity()
    result = trade_service.detect_wish_stop(
        user_id, trade_id
    )
    return jsonify(result), 200


@trades_bp.route("/<trade_id>", methods=["DELETE"])
@jwt_required()
def delete_trade(trade_id):
    """Permanently delete a trade."""
    user_id = get_jwt_identity()
    trade_service.delete_trade(user_id, trade_id)
    return jsonify({"message": "Trade deleted."}), 200


@trades_bp.route(
    "/<trade_id>/restore", methods=["POST"]
)
@jwt_required()
def restore_trade(trade_id):
    """Restore a soft-deleted trade."""
    user_id = get_jwt_identity()
    trade = trade_service.restore_trade(
        user_id, trade_id
    )
    return jsonify({"trade": trade}), 200


@trades_bp.route("/search", methods=["GET"])
@jwt_required()
def search_trades():
    """
    Full-text search on trades.

    Query param: q (search query)
    """
    user_id = get_jwt_identity()
    query = request.args.get("q", "")
    if not query:
        raise ValidationError("Search query is required.")

    trades = trade_service.search_trades(user_id, query)
    return jsonify({"trades": trades}), 200


@trades_bp.route("/symbols", methods=["GET"])
@jwt_required()
def list_symbols():
    """Return distinct symbols from user's closed trades."""
    user_id = get_jwt_identity()
    symbols = trade_service.list_symbols(user_id)
    return jsonify({"symbols": symbols}), 200
