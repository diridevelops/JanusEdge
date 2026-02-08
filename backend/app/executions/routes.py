"""Execution API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.executions import executions_bp
from app.repositories.execution_repo import (
    ExecutionRepository,
)
from app.utils.errors import NotFoundError

exec_repo = ExecutionRepository()


@executions_bp.route("", methods=["GET"])
@jwt_required()
def list_executions():
    """
    List executions with optional filters.

    Query params: trade_id, symbol, account,
        date_from, date_to, page, per_page
    """
    user_id = get_jwt_identity()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 25))
    skip = (page - 1) * per_page

    from bson import ObjectId
    from datetime import datetime

    filters = {}
    trade_id = request.args.get("trade_id")
    if trade_id:
        filters["trade_id"] = ObjectId(trade_id)
    symbol = request.args.get("symbol")
    if symbol:
        filters["symbol"] = symbol.upper()

    date_from = request.args.get("date_from")
    if date_from:
        filters.setdefault("timestamp", {})
        filters["timestamp"]["$gte"] = (
            datetime.fromisoformat(date_from)
        )
    date_to = request.args.get("date_to")
    if date_to:
        filters.setdefault("timestamp", {})
        filters["timestamp"]["$lte"] = (
            datetime.fromisoformat(date_to)
        )

    executions = exec_repo.find_by_user(
        user_id, filters, skip=skip, limit=per_page
    )
    total = exec_repo.count_by_user(user_id, filters)

    return jsonify({
        "executions": [
            exec_repo.serialize_doc(e)
            for e in executions
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }), 200


@executions_bp.route(
    "/<execution_id>", methods=["GET"]
)
@jwt_required()
def get_execution(execution_id):
    """Get a single execution by ID."""
    user_id = get_jwt_identity()
    execution = exec_repo.find_by_id(execution_id)

    if not execution:
        raise NotFoundError("Execution not found.")
    if str(execution["user_id"]) != user_id:
        raise NotFoundError("Execution not found.")

    return jsonify({
        "execution": exec_repo.serialize_doc(execution)
    }), 200
