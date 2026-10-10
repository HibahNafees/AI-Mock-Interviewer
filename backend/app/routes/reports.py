from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError

from ..extensions import db
from ..models import Answer, Question
from ..services import afterwards, limits, reports, scoring
from .common import current_user_id, first_error
from .sessions import TurnBody, owned_session

bp = Blueprint("reports", __name__)


@bp.get("/<int:session_id>/report")
@jwt_required()
def get_report(session_id: int):
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    report = reports.get_report(session)
    if report is None:
        return jsonify(error="No report yet"), 404
    return jsonify(report=reports.report_dict(session, report))


@bp.post("/<int:session_id>/report")
@jwt_required()
def create_report(session_id: int):
    """Start (or resume) building the report; poll GET for progress."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.mode == "reverse":
        return jsonify(error="Reverse interviews have their own feedback"), 409
    if session.status != "completed":
        return jsonify(error="Finish the interview to get your report"), 409
    report = reports.request_report(session)
    return jsonify(report=reports.report_dict(session, report)), 202


@bp.post("/<int:session_id>/questions/<int:question_id>/retry")
@jwt_required()
def retry(session_id: int, question_id: int):
    """ "Try again" on a question: score the new answer and show before/after."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status != "completed":
        return jsonify(error="Finish the interview before retrying questions"), 409
    question = db.session.get(Question, question_id)
    first = db.session.scalar(
        db.select(Answer).filter_by(question_id=question_id, attempt_no=1)
    )
    if (
        question is None
        or question.session_id != session.id
        or question.follow_up_of_id is not None
        or first is None
    ):
        return jsonify(error="Question not found"), 404
    try:
        body = TurnBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    user_id = current_user_id()
    limits.check_can_retry(user_id)
    answer = reports.retry(
        user_id, session, question, body.text, body.duration_ms, body.input_mode
    )
    evals = reports.evaluations_for([first.id, answer.id])
    before = evals.get(first.id)
    return (
        jsonify(
            attempt={
                "attempt_no": answer.attempt_no,
                "answer": answer.transcript,
                "input_mode": answer.input_mode,
                "evaluation": scoring.evaluation_dict(evals.get(answer.id)),
            },
            before_score=before.score if before else None,
        ),
        201,
    )


@bp.get("/<int:session_id>/cheatsheet")
@jwt_required()
def cheat_sheet(session_id: int):
    """One-page prep sheet from the user's own stories, numbers and weak spots."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    report = reports.get_report(session)
    if report is None or report.status != "ready":
        return jsonify(error="The report isn't ready yet"), 409
    return jsonify(sheet=afterwards.cheat_sheet(session, report))


@bp.post("/<int:session_id>/thank-you")
@jwt_required()
def thank_you(session_id: int):
    """A drafted thank-you email (one Fire call, then kept)."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    report = reports.get_report(session)
    if report is None or report.status != "ready":
        return jsonify(error="The report isn't ready yet"), 409
    limits.check_budget()
    return jsonify(email=afterwards.thank_you(current_user_id(), session, report))
