from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models import User
from ..services import admin
from .common import current_user_id

bp = Blueprint("admin", __name__)


@bp.get("/usage")
@jwt_required()
def usage():
    """Daily usage and Fire spend for the admins in ADMIN_EMAILS."""
    if not admin.is_admin(db.session.get(User, current_user_id())):
        return jsonify(error="Not found"), 404
    return jsonify(usage=admin.usage())
