from typing import Literal

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..extensions import db
from ..models import Answer, Session, User
from ..services import interviewer, limits, planning, voice
from ..services.transcription import TranscriptionError, transcribe
from ..services.timer import timer_state
from .common import current_user_id, first_error
from .documents import owned_document

bp = Blueprint("sessions", __name__)

MAX_ANSWER_CHARS = 8000
MAX_ANSWER_MS = 5 * 60 * 1000
# The browser stops recording at 5 minutes; allow a little slack for timing.
DURATION_SLACK_MS = 10 * 1000


class CreateBody(BaseModel):
    resume_id: int
    jd_id: int
    duration_min: int = Field(ge=5, le=60)
    difficulty: Literal["entry", "mid", "senior"] = "mid"
    persona: Literal["friendly", "neutral", "tough"] = "neutral"
    focus: str = Field(default=planning.MIXED, max_length=40)


class PlanSectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    module: str = "behavioral"
    minutes: int = Field(ge=1, le=60)
    questions: list[str] = Field(min_length=1, max_length=8)
    scenario: planning.Scenario | None = None

    @field_validator("questions")
    @classmethod
    def non_empty(cls, v: list[str]) -> list[str]:
        v = [q.strip() for q in v if q.strip()]
        if not v:
            raise ValueError("Each section needs at least one question")
        if any(len(q) > 1000 for q in v):
            raise ValueError("Questions must be under 1000 characters")
        return v


class PlanIn(BaseModel):
    sections: list[PlanSectionIn] = Field(min_length=1, max_length=6)
    reserve: list[planning.BonusOut] = Field(default_factory=list, max_length=6)


class TurnBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    duration_ms: int | None = Field(
        default=None, ge=0, le=MAX_ANSWER_MS + DURATION_SLACK_MS
    )
    input_mode: Literal["text", "voice"] = "text"
    # Ask for Fire audio of the reply (only used when VOICE_PROVIDER=fire).
    speak: bool = False

    @field_validator("text")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Type an answer first")
        return v


def owned_session(session_id: int) -> Session | None:
    s = db.session.get(Session, session_id)
    return s if s is not None and s.user_id == current_user_id() else None


def _transcript(session: Session) -> list[dict]:
    asked = interviewer.asked_questions(session)
    answers = {
        a.question_id: a
        for a in db.session.scalars(
            db.select(Answer)
            .where(Answer.question_id.in_([q.id for q in asked]))
            .filter_by(attempt_no=1)
        )
    }
    out = []
    for q in asked:
        a = answers.get(q.id)
        out.append(
            {
                "question_id": q.id,
                "section": q.section,
                "interviewer": q.asked_text or q.text,
                "segments": q.asked_segments
                or [{"who": "interviewer", "text": q.asked_text or q.text}],
                "is_follow_up": q.follow_up_of_id is not None,
                "is_bonus": q.is_bonus,
                "answer": a.transcript if a else None,
                "duration_ms": a.duration_ms if a else None,
                "input_mode": a.input_mode if a else None,
            }
        )
    return out


def session_dict(session: Session, detail: bool = False) -> dict:
    plan = session.plan_json or {}
    data = {
        "id": session.id,
        "status": session.status,
        "mode": session.mode,
        "duration_min": session.duration_min,
        "difficulty": session.difficulty,
        "persona": session.persona,
        "role_title": plan.get("role_title", ""),
        "focus": plan.get("focus", planning.MIXED),
        "resume_id": session.resume_id,
        "jd_id": session.jd_id,
        "started_at": (
            session.started_at.isoformat() + "Z" if session.started_at else None
        ),
        "ended_at": session.ended_at.isoformat() + "Z" if session.ended_at else None,
        "created_at": session.created_at.isoformat() + "Z",
    }
    if detail:
        data["analysis"] = plan.get("analysis")
        data["plan"] = planning.plan_view(session)
        data["rubric"] = session.rubric_json
        data["voice"] = voice.info(session)
        data["transcript"] = _transcript(session)
        data["timer"] = (
            timer_state(session, interviewer.asked_questions(session)).to_dict()
            if session.started_at
            else None
        )
    return data


@bp.post("")
@jwt_required()
def create():
    """Analyze the JD, then build the question plan and rubric (3 Fire chat calls at most)."""
    try:
        body = CreateBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    user_id = current_user_id()
    resume = owned_document(body.resume_id, "resume")
    jd = owned_document(body.jd_id, "job_description")
    if resume is None or jd is None:
        return jsonify(error="Choose your résumé and a job description first"), 404

    limits.check_can_plan(user_id)
    limits.check_can_start(user_id, body.duration_min)
    analysis = planning.analyze_jd(user_id, jd)
    if body.focus != planning.MIXED and body.focus not in planning.offered_modules(
        analysis
    ):
        return jsonify(error="That interview type doesn't fit this job"), 400
    plan = planning.build_plan(
        user_id, resume, analysis, body.duration_min, body.difficulty, body.focus
    )
    rubric = planning.build_rubric(user_id, analysis, body.difficulty, body.focus)

    summary = planning.analysis_summary(analysis)
    session = Session(
        user_id=user_id,
        resume_id=resume.id,
        jd_id=jd.id,
        mode="standard",
        duration_min=body.duration_min,
        difficulty=body.difficulty,
        persona=body.persona,
        status="planned",
        rubric_json=rubric.model_dump(),
        plan_json={
            "analysis": summary,
            "jd_analysis_id": analysis.id,
            "focus": body.focus,
        },
    )
    db.session.add(session)
    db.session.flush()
    planning.save_plan(session, plan, role_title=summary["role_title"])
    return jsonify(session=session_dict(session, detail=True)), 201


@bp.get("")
@jwt_required()
def list_sessions():
    rows = db.session.scalars(
        db.select(Session)
        .filter_by(user_id=current_user_id())
        .order_by(Session.created_at.desc())
        .limit(50)
    )
    return jsonify(sessions=[session_dict(s) for s in rows])


@bp.get("/<int:session_id>")
@jwt_required()
def get_session(session_id: int):
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    return jsonify(session=session_dict(session, detail=True))


@bp.put("/<int:session_id>/plan")
@jwt_required()
def edit_plan(session_id: int):
    """Replace the question plan before the interview starts."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status != "planned":
        return (
            jsonify(error="The plan can't change once the interview has started"),
            409,
        )
    try:
        body = PlanIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    total = sum(s.minutes for s in body.sections)
    if total != session.duration_min:
        return (
            jsonify(
                error=f"Section minutes add up to {total}; "
                f"they must add up to {session.duration_min}"
            ),
            400,
        )
    names = [s.name.strip() for s in body.sections]
    if len(set(names)) != len(names):
        return jsonify(error="Section names must be different"), 400

    try:
        plan = planning.PlanOut.model_validate(body.model_dump())
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400
    planning.save_plan(session, plan)
    return jsonify(session=session_dict(session, detail=True))


@bp.post("/<int:session_id>/start")
@jwt_required()
def start(session_id: int):
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status != "planned":
        return jsonify(error="This interview has already started"), 409
    user_id = current_user_id()
    limits.check_can_start(user_id, session.duration_min)
    user = db.session.get(User, user_id)
    first = interviewer.start(session, user.name)
    limits.record_session_start(user_id, session.duration_min)
    speak = bool((request.get_json(silent=True) or {}).get("speak"))
    speech = voice.synthesize(user_id, session, first.asked_segments) if speak else None
    return jsonify(session=session_dict(session, detail=True), speech=speech)


@bp.post("/<int:session_id>/turns")
@jwt_required()
def turn(session_id: int):
    """Typed answer to the current question → the interviewer's next message."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status != "active":
        return jsonify(error="This interview is not in progress"), 409
    try:
        body = TurnBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    user_id = current_user_id()
    result = interviewer.take_turn(
        session, user_id, body.text, body.duration_ms, body.input_mode
    )
    speech = (
        voice.synthesize(user_id, session, result["segments"]) if body.speak else None
    )
    return jsonify(
        turn=result, session=session_dict(session, detail=True), speech=speech
    )


@bp.post("/<int:session_id>/transcribe")
@jwt_required()
def transcribe_answer(session_id: int):
    """Spoken answer clip (multipart field "audio") → text. The clip is not stored.

    The browser then sends the text to /turns (or a report's "Try again"), so a
    failed chat call can be retried without paying to transcribe the clip again.
    """
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status == "completed":
        limits.check_can_retry(current_user_id())
    elif session.status != "active":
        return jsonify(error="This interview is not in progress"), 409
    clip = request.files.get("audio")
    if clip is None:
        return jsonify(error="audio is required"), 400
    limit = current_app.config["MAX_AUDIO_BYTES"]
    audio = clip.read(limit + 1)
    if len(audio) > limit:
        return (
            jsonify(
                error="That recording is too long; answers are capped at 5 minutes"
            ),
            413,
        )
    try:
        text = transcribe(current_user_id(), audio, clip.mimetype)
    except TranscriptionError as err:
        return jsonify(error=err.message), err.status
    return jsonify(text=text)


@bp.post("/<int:session_id>/end")
@jwt_required()
def end(session_id: int):
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status == "planned":
        session.status = "abandoned"
        db.session.commit()
    elif session.status == "active":
        interviewer.end(session)
    return jsonify(session=session_dict(session, detail=True))
