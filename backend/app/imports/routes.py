"""CSV Import API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)
from marshmallow import (
    ValidationError as MarshmallowError,
)

from app.imports import imports_bp
from app.imports.schemas import FinalizeSchema
from app.imports.service import ImportService
from app.repositories.import_batch_repo import (
    ImportBatchRepository,
)
from app.repositories.execution_repo import (
    ExecutionRepository,
)
from app.repositories.trade_repo import TradeRepository
from app.repositories.user_repo import UserRepository
from app.utils.errors import NotFoundError, ValidationError
from app.whatif.cache import clear_simulation_cache

import_service = ImportService()
batch_repo = ImportBatchRepository()
exec_repo = ExecutionRepository()
trade_repo = TradeRepository()
user_repo = UserRepository()
finalize_schema = FinalizeSchema()


@imports_bp.route("/upload", methods=["POST"])
@jwt_required()
def upload():
    """
    Upload and parse a CSV file.

    Expects: multipart/form-data with 'file' field.
    Returns: Parsed executions, errors, platform info.
    """
    user_id = get_jwt_identity()

    if "file" not in request.files:
        raise ValidationError("No file provided.")

    file = request.files["file"]
    if file.filename == "":
        raise ValidationError("No file selected.")

    if not file.filename.lower().endswith(".csv"):
        raise ValidationError(
            "Only CSV files are supported."
        )

    content = file.read()
    if len(content) == 0:
        raise ValidationError("File is empty.")

    # Get user timezone
    user = user_repo.find_by_id(user_id)
    user_timezone = (
        user.get("timezone") if user else None
    )

    result = import_service.upload_and_parse(
        file_content=content,
        file_name=file.filename,
        user_id=user_id,
        user_timezone=user_timezone,
    )
    return jsonify(result), 200


@imports_bp.route("/reconstruct", methods=["POST"])
@jwt_required()
def reconstruct():
    """
    Reconstruct trades from parsed executions.

    Expects JSON: {executions[], method?}
    Returns: {trades[]}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    executions = data.get("executions")
    if not executions:
        raise ValidationError("Executions are required.")

    method = data.get("method", "FIFO")

    trades = import_service.reconstruct(
        executions_data=executions,
        method=method,
    )
    return jsonify({"trades": trades}), 200


@imports_bp.route("/finalize", methods=["POST"])
@jwt_required()
def finalize():
    """
    Finalize import: persist trades and executions.

    Expects JSON: {file_hash, platform, file_name,
        trades[], fees{}}
    Returns: Import summary.
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = finalize_schema.load(data)
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    # Build fees dictionary from trades
    fees = {}
    initial_risks = {}
    for trade in validated["trades"]:
        fees[str(trade["index"])] = trade.get(
            "fee", 0.0
        )
        initial_risks[str(trade["index"])] = trade.get(
            "initial_risk"
        )

    # Get all_executions and file info from request
    all_executions = data.get("executions", [])
    if not all_executions:
        raise ValidationError(
            "Executions data is required for "
            "finalization."
        )

    file_size = data.get("file_size", 0)
    column_mapping = data.get("column_mapping")

    user = user_repo.find_by_id(user_id)
    user_timezone = (
        user.get("timezone") if user else None
    )

    result = import_service.finalize(
        user_id=user_id,
        file_hash=validated["file_hash"],
        file_name=validated["file_name"],
        file_size=file_size,
        platform=validated["platform"],
        trades_data=validated["trades"],
        all_executions=all_executions,
        fees=fees,
        initial_risks=initial_risks,
        reconstruction_method=validated[
            "reconstruction_method"
        ],
        user_timezone=user_timezone,
        column_mapping=column_mapping,
    )
    return jsonify(result), 201


@imports_bp.route("/batches", methods=["GET"])
@jwt_required()
def list_batches():
    """
    List import batches for current user.

    Returns: {batches[]}
    """
    user_id = get_jwt_identity()
    batches = batch_repo.find_by_user(user_id)

    return jsonify(
        {
            "batches": [
                batch_repo.serialize_doc(b)
                for b in batches
            ]
        }
    ), 200


@imports_bp.route(
    "/batches/<batch_id>", methods=["GET"]
)
@jwt_required()
def get_batch(batch_id):
    """
    Get import batch details with trades and
    executions.

    Returns: {batch, trades[], executions[]}
    """
    user_id = get_jwt_identity()
    batch = batch_repo.find_by_id(batch_id)

    if not batch:
        raise NotFoundError("Import batch not found.")

    if str(batch["user_id"]) != user_id:
        raise NotFoundError("Import batch not found.")

    from bson import ObjectId

    batch_oid = ObjectId(batch_id)
    executions = exec_repo.find_by_batch(batch_oid)
    trades = trade_repo.find_many(
        {
            "user_id": ObjectId(user_id),
            "import_batch_id": batch_oid,
            "is_deleted": False,
        }
    )

    return jsonify(
        {
            "batch": batch_repo.serialize_doc(batch),
            "trades": [
                trade_repo.serialize_doc(t)
                for t in trades
            ],
            "executions": [
                exec_repo.serialize_doc(e)
                for e in executions
            ],
        }
    ), 200


@imports_bp.route(
    "/batches/<batch_id>", methods=["DELETE"]
)
@jwt_required()
def delete_batch(batch_id):
    """
    Delete an import batch and all related data.

    Returns: {message}
    """
    user_id = get_jwt_identity()
    batch = batch_repo.find_by_id(batch_id)

    if not batch:
        raise NotFoundError("Import batch not found.")

    if str(batch["user_id"]) != user_id:
        raise NotFoundError("Import batch not found.")

    from bson import ObjectId

    batch_oid = ObjectId(batch_id)

    # Delete related executions
    exec_repo.delete_many(
        {"import_batch_id": batch_oid}
    )

    # Delete related trades
    trade_repo.delete_many(
        {"import_batch_id": batch_oid}
    )

    # Delete the batch itself
    batch_repo.delete_one(batch_id)

    clear_simulation_cache()

    return jsonify(
        {"message": "Import batch deleted."}
    ), 200
