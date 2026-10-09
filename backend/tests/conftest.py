import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db


@pytest.fixture()
def fire():
    from tests.fakes import FakeFire

    return FakeFire()


@pytest.fixture()
def app(fire):
    app = create_app(TestConfig)
    app.extensions["fire"] = fire
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


@pytest.fixture()
def auth(signup):
    """Authorization header for a fresh user."""
    token = signup().get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
