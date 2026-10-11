import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..extensions import db
from ..models import User
from ..services import privacy
from .common import first_error

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignupBody(BaseModel):
    email: str
    password: str
    name: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v) or len(v) > 255:
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        return v

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("Name must be 1-120 characters")
        return v


class LoginBody(BaseModel):
    email: str
    password: str


def _token_response(user: User, status: int = 200):
    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token, user=user.to_dict()), status


@bp.post("/signup")
def signup():
    try:
        body = SignupBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    if db.session.scalar(db.select(User).filter_by(email=body.email)):
        return jsonify(error="An account with this email already exists"), 409

    user = User(email=body.email, name=body.name)
    user.set_password(body.password)
    db.session.add(user)
    db.session.commit()
    return _token_response(user, 201)


@bp.post("/login")
def login():
    try:
        body = LoginBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    user = db.session.scalar(
        db.select(User).filter_by(email=body.email.strip().lower())
    )
    if user is None or not user.check_password(body.password):
        return jsonify(error="Incorrect email or password"), 401
    return _token_response(user)


class DeleteBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@bp.delete("/me")
@jwt_required()
def delete_me():
    """ "Delete my data": the account and everything saved for it, in one step."""
    try:
        body = DeleteBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        return jsonify(error="Enter your password to confirm"), 400
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return jsonify(error="Account not found"), 404
    if not user.check_password(body.password):
        return jsonify(error="Incorrect password"), 403
    privacy.delete_user(user.id)
    return jsonify(ok=True)


@bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return jsonify(error="Account not found"), 404
    return jsonify(user=user.to_dict())
