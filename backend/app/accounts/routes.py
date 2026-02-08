"""Trade Account API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.accounts import accounts_bp
from app.repositories.account_repo import (
    AccountRepository,
)
from app.utils.errors import NotFoundError, ValidationError

account_repo = AccountRepository()


@accounts_bp.route("", methods=["GET"])
@jwt_required()
def list_accounts():
    """List all trade accounts for the current user."""
    user_id = get_jwt_identity()
    accounts = account_repo.find_by_user(user_id)
    return jsonify({
        "accounts": [
            account_repo.serialize_doc(a)
            for a in accounts
        ]
    }), 200


@accounts_bp.route(
    "/<account_id>", methods=["PUT"]
)
@jwt_required()
def update_account(account_id):
    """
    Update a trade account.

    Expects JSON: {display_name?, notes?, status?}
    """
    user_id = get_jwt_identity()
    account = account_repo.find_by_id(account_id)

    if not account:
        raise NotFoundError("Account not found.")
    if str(account["user_id"]) != user_id:
        raise NotFoundError("Account not found.")

    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    updates = {}
    if "display_name" in data:
        updates["display_name"] = data["display_name"]
    if "notes" in data:
        updates["notes"] = data["notes"]
    if "status" in data:
        updates["status"] = data["status"]

    if updates:
        account_repo.update_account(
            account_id, updates
        )

    account = account_repo.find_by_id(account_id)
    return jsonify({
        "account": account_repo.serialize_doc(account)
    }), 200
