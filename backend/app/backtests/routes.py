"""Authenticated Backtest run, catalog, and notice routes."""

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import ValidationError as MarshmallowError

from app.backtests import backtest_bp
from app.backtests.simulation_effects import BacktestSimulationEffects
from app.backtests.simulation_repository import BacktestSimulationRepository
from app.backtests.simulation_schemas import (
    AdvanceSimulationRequestSchema,
    CancelOrderRequestSchema,
    ClosePositionRequestSchema,
    ModifyProtectionRequestSchema,
    ResetSimulationRequestSchema,
    RewindSimulationRequestSchema,
    SubmitOrderRequestSchema,
)
from app.backtests.simulation_service import SimulationService
from app.backtests.schemas import serialize_backtest_value
from app.backtests.service import BacktestService
from app.utils.errors import ConflictError, NotFoundError, ValidationError


backtest_service = BacktestService()
simulation_repository = BacktestSimulationRepository()
simulation_effects = BacktestSimulationEffects(
    backtest_repository=backtest_service.repository,
    simulation_repository=simulation_repository,
)
simulation_service = SimulationService(
    backtest_repository=backtest_service.repository,
    simulation_repository=simulation_repository,
)


def _request_json() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("A JSON request body is required.")
    return payload


def _simulation_run_and_precision(user_id: str, run_id: str) -> tuple[dict, int | None]:
    run = backtest_service.repository.find_owned_run(user_id, run_id)
    if run is None:
        raise NotFoundError("Backtest run not found.")
    if run.get("status") == "deleting":
        raise ConflictError("Backtest run is being deleted.")
    metadata = run.get("instrument_metadata") or {}
    precision = metadata.get("price_precision")
    return run, precision if isinstance(precision, int) and not isinstance(precision, bool) else None


def _simulation_payload(schema_type, user_id: str, run_id: str) -> dict:
    _run, precision = _simulation_run_and_precision(user_id, run_id)
    try:
        return schema_type(instrument_precision=precision).load(_request_json())
    except MarshmallowError as exc:
        raise ValidationError("Validation failed.", details=exc.messages) from exc


def _execute_simulation(run_id: str, kind: str, schema_type):
    user_id = get_jwt_identity()
    payload = _simulation_payload(schema_type, user_id, run_id)
    response = simulation_service.execute_operation(
        user_id,
        run_id,
        client_operation_id=payload["client_operation_id"],
        expected_revision=payload["expected_revision"],
        kind=kind,
        request=payload,
        effect_handler=simulation_effects.apply_operation,
        cleanup_handler=simulation_effects.cleanup_generation,
    )
    return jsonify(serialize_backtest_value(response)), 200


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
        period_selection=payload.get("period_selection"),
        period_months=payload.get("period_months"),
        blind_mode=payload.get("blind_mode"),
        initial_balance_usd=payload.get("initial_balance_usd", 10_000),
        risk_percent=payload.get("risk_percent", 1.0),
        execution_costs=payload.get("execution_costs"),
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


@backtest_bp.route("/runs/<run_id>", methods=["DELETE"])
@jwt_required()
def delete_run(run_id: str):
    """Start permanent owner-scoped cleanup; 202 means pending, not done."""
    run = backtest_service.delete_run(get_jwt_identity(), run_id)
    return jsonify({"run": run}), 202


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
    user_id = get_jwt_identity()
    run = backtest_service.repository.find_owned_run(user_id, run_id)
    if run is None:
        raise NotFoundError("Backtest run not found.")
    control = run.get("simulation_control") or {}
    if int(control.get("committed_sequence", 0)) > 0 or control.get("has_accepted_order"):
        raise ConflictError("Use the simulation rewind operation to move the cursor.")
    cursor = backtest_service.save_replay_position(
        user_id,
        run_id,
        source_candle_index=payload.get("source_candle_index"),
        time_ms=payload.get("time_ms"),
        expected_revision=payload.get("expected_revision"),
    )
    return jsonify(
        {"replay_cursor": serialize_backtest_value(cursor)}
    ), 200


@backtest_bp.route("/runs/<run_id>/simulation", methods=["GET"])
@jwt_required()
def get_simulation_state(run_id: str):
    state = simulation_effects.get_state(get_jwt_identity(), run_id)
    return jsonify(serialize_backtest_value(state)), 200


@backtest_bp.route("/runs/<run_id>/simulation/orders", methods=["POST"])
@jwt_required()
def submit_simulation_order(run_id: str):
    return _execute_simulation(run_id, "submit_order", SubmitOrderRequestSchema)


@backtest_bp.route("/runs/<run_id>/simulation/orders/<order_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_simulation_order(run_id: str, order_id: str):
    payload = _simulation_payload(CancelOrderRequestSchema, get_jwt_identity(), run_id)
    payload["order_id"] = order_id
    response = simulation_service.execute_operation(
        get_jwt_identity(), run_id,
        client_operation_id=payload["client_operation_id"],
        expected_revision=payload["expected_revision"], kind="cancel_order",
        request=payload, effect_handler=simulation_effects.apply_operation,
        cleanup_handler=simulation_effects.cleanup_generation,
    )
    return jsonify(serialize_backtest_value(response)), 200


@backtest_bp.route("/runs/<run_id>/simulation/positions/<position_id>/close", methods=["POST"])
@jwt_required()
def close_simulation_position(run_id: str, position_id: str):
    payload = _simulation_payload(ClosePositionRequestSchema, get_jwt_identity(), run_id)
    payload["position_id"] = position_id
    response = simulation_service.execute_operation(
        get_jwt_identity(), run_id,
        client_operation_id=payload["client_operation_id"],
        expected_revision=payload["expected_revision"], kind="close_position",
        request=payload, effect_handler=simulation_effects.apply_operation,
        cleanup_handler=simulation_effects.cleanup_generation,
    )
    return jsonify(serialize_backtest_value(response)), 200


@backtest_bp.route("/runs/<run_id>/simulation/positions/<position_id>/protection", methods=["PUT"])
@jwt_required()
def modify_simulation_protection(run_id: str, position_id: str):
    payload = _simulation_payload(ModifyProtectionRequestSchema, get_jwt_identity(), run_id)
    payload["position_id"] = position_id
    response = simulation_service.execute_operation(
        get_jwt_identity(), run_id,
        client_operation_id=payload["client_operation_id"],
        expected_revision=payload["expected_revision"], kind="modify_protection",
        request=payload, effect_handler=simulation_effects.apply_operation,
        cleanup_handler=simulation_effects.cleanup_generation,
    )
    return jsonify(serialize_backtest_value(response)), 200


@backtest_bp.route("/runs/<run_id>/simulation/costs", methods=["PUT"])
@jwt_required()
def update_simulation_costs(run_id: str):
    _simulation_run_and_precision(get_jwt_identity(), run_id)
    raise ConflictError("Execution costs are fixed when the run is created.")


@backtest_bp.route("/runs/<run_id>/simulation/advance", methods=["POST"])
@jwt_required()
def advance_simulation(run_id: str):
    return _execute_simulation(run_id, "advance", AdvanceSimulationRequestSchema)


@backtest_bp.route("/runs/<run_id>/simulation/rewind", methods=["POST"])
@jwt_required()
def rewind_simulation(run_id: str):
    return _execute_simulation(run_id, "rewind", RewindSimulationRequestSchema)


@backtest_bp.route("/runs/<run_id>/simulation/reset", methods=["POST"])
@jwt_required()
def reset_simulation(run_id: str):
    return _execute_simulation(run_id, "reset", ResetSimulationRequestSchema)


@backtest_bp.route("/runs/<run_id>/chart-workspace", methods=["GET"])
@jwt_required()
def get_chart_workspace(run_id: str):
    return jsonify(
        backtest_service.get_chart_workspace(get_jwt_identity(), run_id)
    ), 200


@backtest_bp.route("/runs/<run_id>/chart-workspace", methods=["PUT"])
@jwt_required()
def save_chart_workspace(run_id: str):
    payload = _request_json()
    result = backtest_service.save_chart_workspace(
        get_jwt_identity(),
        run_id,
        expected_revision=payload.get("expected_revision"),
        workspace=payload.get("workspace"),
    )
    return jsonify(result), 200


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
