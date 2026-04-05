"""Public client-config routes."""

from flask import jsonify

from app.client_config import client_config_bp
from app.client_config.service import build_client_config


@client_config_bp.route("/client-config", methods=["GET"])
def get_client_config():
    """Return public app config for frontend upload UIs."""

    return jsonify(build_client_config()), 200
