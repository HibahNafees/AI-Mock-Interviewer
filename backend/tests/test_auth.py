def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_signup_returns_token_and_user(signup):
    res = signup(email="  Ada@Example.com ")
    assert res.status_code == 201
    data = res.get_json()
    assert data["access_token"]
    assert data["user"]["email"] == "ada@example.com"
    assert "password_hash" not in data["user"]


def test_password_is_hashed(app, signup):
    from app.models import User

    signup()
    user = User.query.one()
    assert user.password_hash != "correct-horse"
    assert user.check_password("correct-horse")


def test_signup_duplicate_email(signup):
    signup()
    res = signup(email="ADA@example.com")
    assert res.status_code == 409


def test_signup_validation(signup, client):
    assert signup(email="not-an-email").status_code == 400
    res = signup(password="short")
    assert res.status_code == 400
    assert "8 characters" in res.get_json()["error"]
    assert signup(name="   ").status_code == 400
    res = client.post("/api/auth/signup", json={})
    assert res.status_code == 400


def test_login(signup, client):
    signup()
    res = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "correct-horse"},
    )
    assert res.status_code == 200
    assert res.get_json()["access_token"]


def test_login_wrong_password(signup, client):
    signup()
    res = client.post(
        "/api/auth/login", json={"email": "ada@example.com", "password": "wrong-pass"}
    )
    assert res.status_code == 401
    res = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert res.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer junk"})
    assert res.status_code == 401


def test_me_with_token(signup, client):
    token = signup().get_json()["access_token"]
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.get_json()["user"]["name"] == "Ada"
