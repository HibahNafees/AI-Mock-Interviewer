from typing import Literal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import BaseModel, Field, ValidationError

from ..extensions import db
from ..models import Session
from ..services import limits, reverse
from ..services.fire import FireError
from .common import current_user_id, first_error
from .documents import owned_document

bp = Blueprint("reverse", __name__)


class StartBody(BaseModel):
    jd_id: int
    profile: Literal["surprise", "strong", "average", "weak", "exaggerating"] = (
        "surprise"
    )
    duration_min: int = Field(default=10, ge=5, le=30)


class AskBody(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    input_mode: Literal["text", "voice"] = "text"


class DecideBody(BaseModel):
    decision: Literal["hire", "no_hire"]
    reasons: str = Field(min_length=3, max_length=2000)


def owned(session_id: int) -> Session | None:
    s = db.session.get(Session, session_id)
    return s if s and s.user_id == current_user_id() and s.mode == "reverse" else None


def _body(model):
    try:
        return model.model_validate(request.get_json(silent=True) or {}), None
    except ValidationError as err:
        return None, (jsonify(error=first_error(err)), 400)


@bp.post("")
@jwt_required()
def start():
    """Create the AI candidate (one Fire call) for a saved job description."""
    body, err = _body(StartBody)
    if err:
        return err
    jd = owned_document(body.jd_id, "job_description")
    if jd is None:
        return jsonify(error="Job description not found"), 404
    user_id = current_user_id()
    limits.check_can_start(user_id, body.duration_min)
    session = reverse.start(user_id, jd, body.profile, body.duration_min)
    limits.record_session_start(user_id, body.duration_min)
    return jsonify(reverse=reverse.view(session)), 201


@bp.get("/<int:session_id>")
@jwt_required()
def get(session_id: int):
    s = owned(session_id)
    if s is None:
        return jsonify(error="Interview not found"), 404
    return jsonify(reverse=reverse.view(s))


@bp.post("/<int:session_id>/ask")
@jwt_required()
def ask(session_id: int):
    s = owned(session_id)
    if s is None:
        return jsonify(error="Interview not found"), 404
    body, err = _body(AskBody)
    if err:
        return err
    try:
        reverse.ask(current_user_id(), s, body.text.strip(), body.input_mode)
    except reverse.ReverseError as e:
        return jsonify(error=e.message), e.status
    except FireError as e:
        return jsonify(error=e.message), e.status
    return jsonify(reverse=reverse.view(s))


@bp.post("/<int:session_id>/decide")
@jwt_required()
def decide(session_id: int):
    s = owned(session_id)
    if s is None:
        return jsonify(error="Interview not found"), 404
    body, err = _body(DecideBody)
    if err:
        return err
    try:
        reverse.decide(current_user_id(), s, body.decision, body.reasons.strip())
    except reverse.ReverseError as e:
        return jsonify(error=e.message), e.status
    return jsonify(reverse=reverse.view(s))
