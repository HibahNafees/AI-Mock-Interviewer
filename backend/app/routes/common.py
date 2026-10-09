from flask import jsonify
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError

from ..services.fire import FireError
from ..services.limits import LimitReached


def first_error(err: ValidationError) -> str:
    first = err.errors()[0]
    msg = first["msg"].removeprefix("Value error, ")
    if first["type"] == "missing":
        return f"{first['loc'][0]} is required"
    return msg


def current_user_id() -> int:
    return int(get_jwt_identity())


def register_error_handlers(app) -> None:
    @app.errorhandler(FireError)
    def fire_error(err: FireError):
        return jsonify(error=err.message), err.status

    @app.errorhandler(LimitReached)
    def limit_reached(err: LimitReached):
        return jsonify(error=err.message), 429
