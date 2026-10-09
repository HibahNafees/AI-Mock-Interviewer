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


RESUME = (
    "Ada Lovelace. Backend engineer. Built the Acme billing API in Python and MySQL."
)
JD = (
    "We are hiring a backend engineer to design APIs and tune MySQL databases at scale."
)


@pytest.fixture()
def docs(client, auth):
    def upload(kind, text):
        res = client.post(
            "/api/documents", json={"kind": kind, "text": text}, headers=auth
        )
        return res.get_json()["document"]["id"]

    return {
        "resume_id": upload("resume", RESUME),
        "jd_id": upload("job_description", JD),
    }


@pytest.fixture()
def planned(client, auth, docs):
    res = client.post(
        "/api/sessions",
        json={**docs, "duration_min": 10, "persona": "friendly"},
        headers=auth,
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["session"]
