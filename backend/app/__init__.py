from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .extensions import db, jwt, migrate


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    for key in ("SECRET_KEY", "JWT_SECRET_KEY", "SQLALCHEMY_DATABASE_URI"):
        if not app.config.get(key):
            raise RuntimeError(f"{key} is not set; copy .env.example to .env")

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"])

    from . import models  # noqa: F401  (register tables with SQLAlchemy)
    from .routes.auth import bp as auth_bp
    from .routes.common import register_error_handlers
    from .routes.documents import bp as documents_bp
    from .routes.health import bp as health_bp
    from .routes.sessions import bp as sessions_bp

    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(documents_bp, url_prefix="/api/documents")
    app.register_blueprint(sessions_bp, url_prefix="/api/sessions")
    register_error_handlers(app)

    @jwt.unauthorized_loader
    def missing_token(reason: str):
        return jsonify(error="Please log in"), 401

    @jwt.invalid_token_loader
    def invalid_token(reason: str):
        return jsonify(error="Your session is invalid; please log in again"), 401

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return jsonify(error="Your session expired; please log in again"), 401

    @app.errorhandler(404)
    def not_found(_err):
        return jsonify(error="Not found"), 404

    @app.errorhandler(413)
    def too_large(_err):
        return jsonify(error="That upload is too large"), 413

    @app.errorhandler(405)
    def method_not_allowed(_err):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(500)
    def server_error(_err):
        return jsonify(error="Something went wrong on our side; please try again"), 500

    return app
