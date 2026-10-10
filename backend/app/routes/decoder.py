from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..extensions import db
from ..models import JdDecode
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
    return jsonify(decode=decoder.decode_dict(row))


@bp.get("/<token>")
def shared(token: str):
    """A decoded posting anyone with the link can read."""
    row = db.session.scalar(db.select(JdDecode).filter_by(share_token=token))
    if row is None:
        return jsonify(error="That decode link doesn't exist"), 404
    return jsonify(decode=decoder.decode_dict(row))
