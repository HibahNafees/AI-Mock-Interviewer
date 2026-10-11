from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..extensions import db
from ..models import Debrief, Session
from ..services import debriefs, limits, reports
from ..services.fire import FireError
from ..services.transcription import TranscriptionError, transcribe
from .common import current_user_id, first_error
from .documents import owned_document

bp = Blueprint("debriefs", __name__)

MAX_ITEMS = 15


class RecalledItem(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    answer: str = Field(min_length=1, max_length=8000)
    input_mode: str = "text"
    duration_ms: int | None = Field(default=None, ge=0, le=310_000)

    @field_validator("question", "answer")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class DebriefBody(BaseModel):
    role: str = Field(min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    round: str | None = Field(default=None, max_length=120)
    resume_id: int | None = None
    jd_id: int | None = None
    items: list[RecalledItem] = Field(min_length=1, max_length=MAX_ITEMS)


def owned_debrief(debrief_id: int) -> Debrief | None:
    d = db.session.get(Debrief, debrief_id)
    return d if d and d.user_id == current_user_id() else None


@bp.post("")
@jwt_required()
def create():
    """Recalled questions and answers from a real interview → a scored debrief."""
    try:
        body = DebriefBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400
    user_id = current_user_id()
    resume = owned_document(body.resume_id, "resume") if body.resume_id else None
    jd = owned_document(body.jd_id, "job_description") if body.jd_id else None
    if (body.resume_id and resume is None) or (body.jd_id and jd is None):
        return jsonify(error="Document not found"), 404
    limits.check_can_plan(user_id)
    limits.check_budget()
    debrief = debriefs.create(
        user_id,
        body.role.strip(),
        (body.company or "").strip() or None,
        (body.round or "").strip() or None,
        [i.model_dump() for i in body.items],
        resume,
        jd,
    )
    reports.request_report(db.session.get(Session, debrief.session_id))
    return jsonify(debrief=debriefs.debrief_dict(debrief)), 201


@bp.post("/transcribe")
@jwt_required()
def transcribe_recall():
    """Your spoken recollection (recorded in this browser) → text. Never a recording
    of the real interview: the clip is transcribed and discarded."""
    clip = request.files.get("audio")
    if clip is None:
        return jsonify(error="audio is required"), 400
    limit = current_app.config["MAX_AUDIO_BYTES"]
    audio = clip.read(limit + 1)
    if len(audio) > limit:
        return (
            jsonify(
                error="That recording is too long; keep each answer under 5 minutes"
            ),
            413,
        )
    limits.check_budget()
    try:
        text = transcribe(current_user_id(), audio, clip.mimetype)
    except TranscriptionError as err:
        return jsonify(error=err.message), err.status
    return jsonify(text=text)


@bp.get("")
@jwt_required()
def list_debriefs():
    rows = db.session.scalars(
        db.select(Debrief)
        .filter_by(user_id=current_user_id())
        .order_by(Debrief.created_at.desc())
    ).all()
    return jsonify(debriefs=[debriefs.debrief_dict(d) for d in rows])


@bp.post("/<int:debrief_id>/predict")
@jwt_required()
def predict(debrief_id: int):
    """Retry the next-round prediction if it failed after the report."""
    d = owned_debrief(debrief_id)
    if d is None:
        return jsonify(error="Debrief not found"), 404
    session = db.session.get(Session, d.session_id)
    items = reports.threads(session)
    done = reports.evaluations_for([t.main_answer.id for t in items])
    limits.check_budget()
    try:
        debriefs.predict(current_user_id(), d, items, done)
    except FireError as err:
        return jsonify(error=err.message), err.status
    return jsonify(debrief=debriefs.debrief_dict(d))


class PracticeBody(BaseModel):
    duration_min: int = Field(default=10, ge=5, le=30)


@bp.post("/<int:debrief_id>/practice")
@jwt_required()
def practice(debrief_id: int):
    """Practice the next round: a planned interview from the predicted questions."""
    d = owned_debrief(debrief_id)
    if d is None:
        return jsonify(error="Debrief not found"), 404
    try:
        body = PracticeBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400
    user_id = current_user_id()
    limits.check_can_start(user_id, body.duration_min)
    session = debriefs.practice_next_round(user_id, d, body.duration_min)
    if session is None:
        return jsonify(error="The next-round questions aren't ready yet"), 409
    from .sessions import session_dict

    return jsonify(session=session_dict(session, detail=True)), 201


@bp.delete("/<int:debrief_id>")
@jwt_required()
def delete(debrief_id: int):
    d = owned_debrief(debrief_id)
    if d is None:
        return jsonify(error="Debrief not found"), 404
    session = db.session.get(Session, d.session_id) if d.session_id else None
    db.session.delete(d)
    db.session.flush()  # before the session, whose delete would cascade to it
    if session is not None:
        db.session.delete(session)
    db.session.commit()
    return jsonify(ok=True)
