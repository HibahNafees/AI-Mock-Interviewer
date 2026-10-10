from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import BaseModel, Field, ValidationError

from ..extensions import db
from ..models import User
from ..services import practice
from ..services.stats import user_stats
from .common import current_user_id, first_error

bp = Blueprint("stats", __name__)


@bp.get("/stats")
@jwt_required()
def stats():
    """The signed-in user's progress for the dashboard."""
    return jsonify(stats=user_stats(current_user_id()))


class GoalBody(BaseModel):
    weekly_goal: int = Field(ge=1, le=14)


@bp.put("/stats/goal")
@jwt_required()
def set_goal():
    """Mock interviews per week the user is aiming for."""
    try:
        body = GoalBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400
    user = db.session.get(User, current_user_id())
    user.weekly_goal = body.weekly_goal
    db.session.commit()
    return jsonify(stats=user_stats(user.id))


@bp.get("/practice")
@jwt_required()
def practice_queue():
    """The question bank: due now, coming back later, and mastered."""
    return jsonify(practice=practice.queue(current_user_id()))
