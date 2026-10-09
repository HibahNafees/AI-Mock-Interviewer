from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from ..services.stats import user_stats
from .common import current_user_id

bp = Blueprint("stats", __name__)


@bp.get("/stats")
@jwt_required()
def stats():
    """The signed-in user's progress for the dashboard."""
    return jsonify(stats=user_stats(current_user_id()))
