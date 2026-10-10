from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import BaseModel, Field, ValidationError

from ..extensions import db
from ..models import Story
from ..models.base import utcnow
from ..services import stories
from .common import current_user_id, first_error
from .documents import owned_document

bp = Blueprint("stories", __name__)


class StoryEdit(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    situation: str | None = Field(default=None, max_length=1000)
    task: str | None = Field(default=None, max_length=1000)
    action: str | None = Field(default=None, max_length=1500)
    result: str | None = Field(default=None, max_length=1000)
    competencies: list[str] | None = Field(default=None, max_length=8)


def owned_story(story_id: int) -> Story | None:
    story = db.session.get(Story, story_id)
    return story if story and story.user_id == current_user_id() else None


@bp.get("")
@jwt_required()
def list_stories():
    """The story bank, strongest first, with competency coverage and gaps."""
    user_id = current_user_id()
    rows = db.session.scalars(db.select(Story).filter_by(user_id=user_id)).all()
    rows.sort(key=lambda s: (-(s.strength or 0), s.title.lower()))
    return jsonify(
        stories=[stories.story_dict(s) for s in rows],
        coverage=stories.coverage(user_id, rows),
    )


@bp.put("/<int:story_id>")
@jwt_required()
def edit_story(story_id: int):
    """Rename or correct a story; the user's wording is never overwritten later."""
    story = owned_story(story_id)
    if story is None:
        return jsonify(error="Story not found"), 404
    try:
        body = StoryEdit.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400
    if body.title is not None:
        story.title = body.title.strip()
    star = dict(story.star_json or {})
    for part in stories.PARTS:
        value = getattr(body, part)
        if value is not None:
            star[part] = value.strip() or None
    story.star_json = star
    if body.competencies is not None:
        story.competencies_json = list(
            dict.fromkeys(c.strip()[:120] for c in body.competencies if c.strip())
        )
    story.user_edited = True
    story.updated_at = utcnow()
    db.session.commit()
    return jsonify(story=stories.story_dict(story))


@bp.delete("/<int:story_id>")
@jwt_required()
def delete_story(story_id: int):
    story = owned_story(story_id)
    if story is None:
        return jsonify(error="Story not found"), 404
    db.session.delete(story)
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/suggest")
@jwt_required()
def suggest():
    """Stories that fit a job description you've chosen (no Fire call)."""
    jd_id = request.args.get("jd_id", type=int)
    if jd_id is None or owned_document(jd_id, "job_description") is None:
        return jsonify(error="Job description not found"), 404
    return jsonify(stories=stories.suggest(current_user_id(), jd_id))
