from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..services import company, limits
from .common import current_user_id

bp = Blueprint("company", __name__)


@bp.post("/research")
@jwt_required()
def research():
    """Read a company's public page and prepare "Why us?" questions (cached)."""
    body = request.get_json(silent=True) or {}
    url = str(body.get("url") or "").strip()
    if not url:
        return jsonify(error="Enter the company's website"), 400
    limits.check_budget()
    try:
        row = company.research(
            current_user_id(), url, str(body.get("role") or "the role")[:120]
        )
    except company.ResearchError as err:
        return jsonify(error=err.message), err.status
    return jsonify(research=company.research_dict(row))
