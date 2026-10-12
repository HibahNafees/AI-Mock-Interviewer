"""Privacy controls: expired documents, "Delete my data", revocable report links."""

from datetime import timedelta

from app.extensions import db
from app.models import (
    AnonSpend,
    Answer,
    Document,
    JdAnalysis,
    Question,
    Report,
    Session,
    UsageLimit,
    User,
)
from app.models.base import utcnow
from app.services.limits import month_spend_usd
from app.services.privacy import purge_expired_documents

from tests.test_reports import build, finished


def test_purge_deletes_only_expired_unsaved_documents(client, auth, planned, docs):
    resume = db.session.get(Document, docs["resume_id"])
    jd = db.session.get(Document, docs["jd_id"])
    resume.expires_at = utcnow() - timedelta(minutes=1)
    jd.expires_at = None  # saved by the user
    db.session.commit()
    jd_analyses = db.session.query(JdAnalysis).count()

    assert purge_expired_documents() == 1
    assert db.session.get(Document, docs["resume_id"]) is None
    assert db.session.get(Document, docs["jd_id"]) is not None
    assert db.session.query(JdAnalysis).count() == jd_analyses
    # The interview keeps its plan, only the link to the résumé is gone.
    session = db.session.get(Session, planned["id"])
    assert session.resume_id is None and session.plan_json


def test_purge_cli(app, client, auth, docs):
    db.session.get(Document, docs["resume_id"]).expires_at = utcnow()
    db.session.commit()
    out = app.test_cli_runner().invoke(args=["purge-expired"])
    assert "Deleted 1 expired documents" in out.output


def test_delete_my_data_needs_the_password(client, auth):
    assert client.delete("/api/auth/me", json={}, headers=auth).status_code == 400
    r = client.delete("/api/auth/me", json={"password": "nope"}, headers=auth)
    assert r.status_code == 403
    assert db.session.query(User).count() == 1


def test_delete_my_data_removes_everything_but_keeps_the_spend(
    client, auth, fire, planned
):
    finished(client, auth, fire, planned["id"])
    assert build(client, auth, planned["id"]).status_code == 202
    spend = month_spend_usd()
    assert spend > 0

    r = client.delete("/api/auth/me", json={"password": "correct-horse"}, headers=auth)
    assert r.status_code == 200
    for model in (User, Document, Session, Question, Answer, Report, UsageLimit):
        assert db.session.query(model).count() == 0, model.__name__
    # The budget still counts what this account spent.
    assert abs(month_spend_usd() - spend) < 1e-9
    assert db.session.query(AnonSpend).count() == 1
    # The old token is refused everywhere, before any Fire work (T-125: it was
    # still accepted, and Fire spend for a missing user went unrecorded).
    calls = len(fire.calls)
    for path in ("/api/auth/me", "/api/sessions", "/api/documents", "/api/stats"):
        assert client.get(path, headers=auth).status_code == 401, path
    r = client.post("/api/company/research", json={"url": "acme.com"}, headers=auth)
    assert r.status_code == 401
    r = client.post(
        "/api/decoder", json={"text": "Backend engineer. " * 20}, headers=auth
    )
    assert r.status_code == 401
    assert "no longer exists" in r.get_json()["error"]
    assert len(fire.calls) == calls


def test_share_link_is_read_only_and_revocable(client, auth, fire, planned, signup):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    assert (
        client.post(f"/api/sessions/{sid}/report/share", headers=auth).status_code
        == 409
    )
    build(client, auth, sid)
    token = client.post(f"/api/sessions/{sid}/report/share", headers=auth).get_json()[
        "share_token"
    ]
    # Sharing twice keeps the same link.
    again = client.post(f"/api/sessions/{sid}/report/share", headers=auth)
    assert again.get_json()["share_token"] == token
    owner = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    assert owner["report"]["share_token"] == token

    public = client.get(f"/api/shared/reports/{token}")  # no login
    assert public.status_code == 200
    body = public.get_json()["report"]
    assert body["shared"] is True and "share_token" not in body
    assert body["questions"]

    # Someone else can't share or revoke it.
    other = signup(email="eve@example.com").get_json()["access_token"]
    eve = {"Authorization": f"Bearer {other}"}
    assert (
        client.delete(f"/api/sessions/{sid}/report/share", headers=eve).status_code
        == 404
    )

    assert (
        client.delete(f"/api/sessions/{sid}/report/share", headers=auth).status_code
        == 200
    )
    assert client.get(f"/api/shared/reports/{token}").status_code == 404
