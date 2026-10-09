import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def signup(client):
    def _signup(email="ada@example.com", password="correct-horse", name="Ada"):
        return client.post(
            "/api/auth/signup",
            json={"email": email, "password": password, "name": name},
        )

    return _signup
