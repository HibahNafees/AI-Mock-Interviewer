"""Deploy hardening: brute-force limits, production settings, proxy addresses."""

import pytest

from app import create_app
from app.config import TestConfig
from app.services import ratelimit


@pytest.fixture()
def limited(app):
    app.config["RATE_LIMITS"] = True
    ratelimit.reset()
    yield app
    ratelimit.reset()


def test_login_is_rate_limited_per_address(limited, client, signup):
    signup()
    bad = {"email": "ada@example.com", "password": "wrong-password"}
    codes = [client.post("/api/auth/login", json=bad).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    # Another address isn't affected.
    r = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "correct-horse"},
        environ_base={"REMOTE_ADDR": "10.0.0.9"},
    )
    assert r.status_code == 200


def test_signup_is_rate_limited(limited, signup):
    codes = [signup(email=f"u{i}@example.com").status_code for i in range(6)]
    assert codes == [201] * 5 + [429]


def test_delete_my_data_password_guesses_are_limited(limited, client, auth):
    codes = [
        client.delete("/api/auth/me", json={"password": "x"}, headers=auth).status_code
        for _ in range(6)
    ]
    assert codes == [403] * 5 + [429]


class Prod(TestConfig):
    APP_ENV = "production"
    SQLALCHEMY_DATABASE_URI = "mysql+pymysql://u:p@db/mock"
    SECRET_KEY = "s" * 40
    JWT_SECRET_KEY = "j" * 40
    FIRE_API_KEY = "fire-key"
    CORS_ORIGINS = ["https://mock.example.app"]


def test_production_starts_with_safe_settings():
    assert create_app(Prod).config["APP_ENV"] == "production"


@pytest.mark.parametrize(
    "override, message",
    [
        ({"SECRET_KEY": "short"}, "SECRET_KEY must be"),
        ({"FIRE_API_KEY": None}, "FIRE_API_KEY is not set"),
        ({"SQLALCHEMY_DATABASE_URI": "sqlite://"}, "must point at MySQL"),
        ({"CORS_ORIGINS": ["http://localhost:5173"]}, "CORS_ORIGINS"),
    ],
)
def test_production_refuses_unsafe_settings(override, message):
    cfg = type("Bad", (Prod,), override)
    with pytest.raises(RuntimeError, match=message):
        create_app(cfg)


def test_trusted_proxy_uses_the_forwarded_client_address():
    cfg = type("Proxied", (TestConfig,), {"TRUST_PROXY": True})
    app = create_app(cfg)

    @app.get("/api/_ip")
    def ip():
        from flask import request

        return request.remote_addr

    r = app.test_client().get(
        "/api/_ip",
        headers={"X-Forwarded-For": "203.0.113.7"},
        environ_base={"REMOTE_ADDR": "172.18.0.5"},
    )
    assert r.text == "203.0.113.7"
