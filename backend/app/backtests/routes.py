"""Authenticated Backtest run, catalog, and notice routes."""

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.backtests import backtest_bp
from app.backtests.schemas import serialize_backtest_value
from app.backtests.service import BacktestService
from app.utils.errors import ValidationError


backtest_service = BacktestService()


def _request_json() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("A JSON request body is required.")
    return payload


@backtest_bp.route("/instruments", methods=["GET"])
@jwt_required()
def list_instruments():
    """Return the current catalog from the pinned downloader."""
    return jsonify({"instruments": backtest_service.get_instruments()}), 200


@backtest_bp.route("/runs", methods=["POST"])
@jwt_required()
def create_run():
    """Create the run/account/job records and return immediately."""
    payload = _request_json()
    run = backtest_service.create_run(
        user_id=get_jwt_identity(),
        instrument=payload.get("instrument"),
        start_date=payload.get("start_date"),
        end_date=payload.get("end_date"),
        display_timezone=payload.get("display_timezone"),
    )
    return jsonify({"run": serialize_backtest_value(run)}), 202


@backtest_bp.route("/runs", methods=["GET"])
@jwt_required()
def list_runs():
    return jsonify(
        {"runs": backtest_service.list_runs(get_jwt_identity())}
    ), 200


@backtest_bp.route("/runs/<run_id>", methods=["GET"])
@jwt_required()
def get_run(run_id: str):
    return jsonify(
        {"run": backtest_service.get_run(get_jwt_identity(), run_id)}
    ), 200


@backtest_bp.route("/runs/<run_id>/candle-dates", methods=["GET"])
@jwt_required()
def list_candle_dates(run_id: str):
    dates = backtest_service.get_available_candle_dates(
        get_jwt_identity(),
        run_id,
        before=request.args.get("before"),
        after=request.args.get("after"),
    )
    return jsonify({"dates": dates}), 200


@backtest_bp.route("/runs/<run_id>/candles", methods=["GET"])
@jwt_required()
def get_candles_for_date(run_id: str):
    candles = backtest_service.get_candles_for_date(
        get_jwt_identity(), run_id, request.args.get("date")
    )
    return jsonify({"candles": candles}), 200


@backtest_bp.route("/runs/<run_id>/replay-position", methods=["PUT"])
@jwt_required()
def save_replay_position(run_id: str):
    payload = _request_json()
    cursor = backtest_service.save_replay_position(
        get_jwt_identity(),
        run_id,
        source_candle_index=payload.get("source_candle_index"),
        time_ms=payload.get("time_ms"),
        expected_revision=payload.get("expected_revision"),
    )
    return jsonify(
        {"replay_cursor": serialize_backtest_value(cursor)}
    ), 200


@backtest_bp.route("/runs/<run_id>/chart-tabs", methods=["PUT"])
@jwt_required()
def save_chart_tabs(run_id: str):
    payload = _request_json()
    tabs = backtest_service.save_chart_tabs(
        get_jwt_identity(), run_id, payload.get("tabs")
    )
    return jsonify({"tabs": tabs}), 200


@backtest_bp.route("/runs/<run_id>/drawings", methods=["GET"])
@jwt_required()
def get_drawing_state(run_id: str):
    drawing_state = backtest_service.get_drawing_state(
        get_jwt_identity(),
        run_id,
        request.args.get("interval_minutes"),
    )
    return jsonify(drawing_state), 200


@backtest_bp.route("/runs/<run_id>/drawings", methods=["PUT"])
@jwt_required()
def save_drawing_state(run_id: str):
    drawing_state = backtest_service.save_drawing_state(
        get_jwt_identity(),
        run_id,
        request.args.get("interval_minutes"),
        _request_json(),
    )
    return jsonify(drawing_state), 200


@backtest_bp.route("/runs/<run_id>/retry", methods=["POST"])
@jwt_required()
def retry_run(run_id: str):
    run = backtest_service.retry_run(get_jwt_identity(), run_id)
    return jsonify({"run": run}), 202


@backtest_bp.route("/notices", methods=["GET"])
@jwt_required()
def list_notices():
    return jsonify(
        {"notices": backtest_service.list_notices(get_jwt_identity())}
    ), 200


@backtest_bp.route("/notices/<notice_id>", methods=["DELETE"])
@jwt_required()
def dismiss_notice(notice_id: str):
    backtest_service.dismiss_notice(get_jwt_identity(), notice_id)
    return jsonify({"message": "Preparation notice dismissed."}), 200
