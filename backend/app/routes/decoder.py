from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..extensions import db
from ..models import JdDecode, SavedDecode
from ..services import decoder
from .documents import owned_document

bp = Blueprint("decoder", __name__)


def _optional_user() -> int | None:
    """The signed-in user, or None: the decoder works without an account."""
    verify_jwt_in_request(optional=True)
    identity = get_jwt_identity()
    return int(identity) if identity else None


@bp.post("")
def decode():
    """Decode a pasted job description (or, signed in, a saved one)."""
    user_id = _optional_user()
    body = request.get_json(silent=True) or {}
    text = body.get("text") or ""
    if body.get("jd_id") is not None and user_id is not None:
        doc = owned_document(int(body["jd_id"]), "job_description")
        if doc is None:
            return jsonify(error="Job description not found"), 404
        text = doc.raw_text
    try:
        row = decoder.decode(str(text), user_id, request.remote_addr)
    except decoder.DecodeError as err:
        return jsonify(error=err.message), err.status
    saved = decoder.save_for(user_id, row, str(text)) if user_id else None
    return jsonify(
        decode={**decoder.decode_dict(row), "saved_id": saved.id if saved else None}
    )


def _owned_saved(saved_id: int) -> SavedDecode | None:
    user_id = _optional_user()
    saved = db.session.get(SavedDecode, saved_id)
    return saved if saved is not None and saved.user_id == user_id else None


@bp.get("/saved")
def saved_list():
    """The signed-in user's decodes, newest first."""
    user_id = _optional_user()
    if user_id is None:
        return jsonify(error="Sign in to see your saved decodes"), 401
    rows = db.session.execute(
        db.select(SavedDecode, JdDecode)
        .join(JdDecode, SavedDecode.decode_id == JdDecode.id)
        .where(SavedDecode.user_id == user_id)
        .order_by(SavedDecode.saved_at.desc())
        .limit(50)
    ).all()
    return jsonify(saved=[decoder.saved_dict(s, d) for s, d in rows])


@bp.delete("/saved/<int:saved_id>")
def delete_saved(saved_id: int):
    saved = _owned_saved(saved_id)
    if saved is None:
        return jsonify(error="Saved decode not found"), 404
    decoder.delete_saved(saved)
    return "", 204


@bp.get("/<token>")
def shared(token: str):
    """A decoded posting anyone with the link can read."""
    row = db.session.scalar(db.select(JdDecode).filter_by(share_token=token))
    if row is None:
        return jsonify(error="That decode link doesn't exist"), 404
    return jsonify(decode=decoder.decode_dict(row))
