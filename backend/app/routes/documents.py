from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models import Document
from ..models.base import utcnow
from .. import modules
from ..services import limits, planning
from ..services.parsing import ParseError, extract_text, validate_text
from .common import current_user_id

bp = Blueprint("documents", __name__)

KINDS = ("resume", "job_description")
RETENTION = timedelta(days=30)


def document_dict(doc: Document, full: bool = False) -> dict:
    data = {
        "id": doc.id,
        "kind": doc.kind,
        "title": doc.title,
        "chars": len(doc.raw_text),
        "preview": doc.raw_text[:300],
        "expires_at": doc.expires_at.isoformat() + "Z" if doc.expires_at else None,
        "created_at": doc.created_at.isoformat() + "Z",
    }
    if full:
        data["text"] = doc.raw_text
    return data


def _default_title(kind: str, text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    label = "Résumé" if kind == "resume" else "Job description"
    return f"{label}: {first_line[:80]}" if first_line else label


@bp.post("")
@jwt_required()
def upload():
    """Upload a résumé or job description as a file (multipart) or pasted text (JSON).

    Only the extracted text is stored; the uploaded file is never written to disk.
    """
    if request.files:
        kind = request.form.get("kind", "")
        file = request.files.get("file")
        title = request.form.get("title")
        if file is None:
            return jsonify(error="file is required"), 400
        data = file.read(current_app.config["MAX_UPLOAD_BYTES"] + 1)
        if len(data) > current_app.config["MAX_UPLOAD_BYTES"]:
            return jsonify(error="That file is too large (5 MB max)"), 413
        name = file.filename or ""
        try:
            text = extract_text(name, data)
        except ParseError as err:
            return jsonify(error=err.message), 400
    else:
        body = request.get_json(silent=True) or {}
        kind = body.get("kind", "")
        title = body.get("title")
        try:
            text = validate_text(str(body.get("text") or ""))
        except ParseError as err:
            return jsonify(error=err.message), 400

    if kind not in KINDS:
        return jsonify(error="kind must be resume or job_description"), 400

    doc = Document(
        user_id=current_user_id(),
        kind=kind,
        title=(title or "").strip()[:255] or _default_title(kind, text),
        raw_text=text,
        expires_at=utcnow() + RETENTION,
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify(document=document_dict(doc)), 201


@bp.get("")
@jwt_required()
def list_documents():
    query = db.select(Document).filter_by(user_id=current_user_id())
    kind = request.args.get("kind")
    if kind:
        query = query.filter_by(kind=kind)
    query = query.where(
        (Document.expires_at.is_(None)) | (Document.expires_at > utcnow())
    ).order_by(Document.created_at.desc())
    return jsonify(documents=[document_dict(d) for d in db.session.scalars(query)])


def owned_document(doc_id: int, kind: str | None = None) -> Document | None:
    doc = db.session.get(Document, doc_id)
    if doc is None or doc.user_id != current_user_id():
        return None
    if kind and doc.kind != kind:
        return None
    if doc.expires_at and doc.expires_at <= utcnow():
        return None
    return doc


@bp.get("/<int:doc_id>")
@jwt_required()
def get_document(doc_id: int):
    doc = owned_document(doc_id)
    if doc is None:
        return jsonify(error="Document not found"), 404
    return jsonify(document=document_dict(doc, full=True))


@bp.post("/<int:doc_id>/analysis")
@jwt_required()
def analyze(doc_id: int):
    """Role detection for a job description (one Fire chat call, cached per document)
    and the interview types that fit it."""
    jd = owned_document(doc_id, "job_description")
    if jd is None:
        return jsonify(error="Job description not found"), 404
    limits.check_budget()
    analysis = planning.analyze_jd(current_user_id(), jd)
    return jsonify(
        analysis=planning.analysis_summary(analysis),
        modules=[
            {
                "name": n,
                "label": modules.MODULES[n].label,
                "blurb": modules.MODULES[n].blurb,
            }
            for n in planning.offered_modules(analysis)
        ],
    )


@bp.delete("/<int:doc_id>")
@jwt_required()
def delete_document(doc_id: int):
    doc = owned_document(doc_id)
    if doc is None:
        return jsonify(error="Document not found"), 404
    db.session.delete(doc)
    db.session.commit()
    return "", 204
