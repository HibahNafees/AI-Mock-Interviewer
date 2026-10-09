"""Dashboard progress numbers."""

from app.extensions import db
from app.models import Report

from tests.test_reports import build, finished, retry
from tests.test_sessions import answer, started


def stats(client, auth):
    res = client.get("/api/stats", headers=auth)
    assert res.status_code == 200
    return res.get_json()["stats"]


def test_new_user_has_empty_stats(client, auth):
    s = stats(client, auth)
    assert s["interviews"] == 0 and s["average_score"] is None
    assert s["history"] == [] and s["roles"] == [] and s["skills"] == []
    assert s["streak_days"] == 0 and s["level"] == 1 and s["next_level_in"] == 2


def test_stats_after_two_interviews(client, auth, docs, fire, planned):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    qid = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()["report"][
        "questions"
    ][0]["question_id"]
    retry(client, auth, sid, qid)

    other = client.post(
        "/api/sessions", json={**docs, "duration_min": 10}, headers=auth
    ).get_json()["session"]["id"]
    started(client, auth, other)
    answer(client, auth, other, "I'd put a token bucket per API key in Redis.")
    client.post(f"/api/sessions/{other}/end", headers=auth)
    build(client, auth, other)
    first = db.session.scalar(db.select(Report).filter_by(session_id=sid))

    s = stats(client, auth)
    assert s["interviews"] == 2
    assert s["questions_answered"] == 3 + 1
    assert s["retries"] == 1
    assert s["practice_minutes"] >= 3
    assert [h["session_id"] for h in s["history"]] == [sid, other]
    assert s["best_score"] == max(h["score"] for h in s["history"])
    assert s["improvement"] == round(s["history"][-1]["score"] - first.overall_score, 2)
    assert s["roles"] == [
        {
            "role": "Backend Engineer",
            "interviews": 2,
            "average_score": s["average_score"],
        }
    ]
    assert {k["name"] for k in s["skills"]} >= {"Structure", "Clarity"}
    assert s["streak_days"] == 1
    assert s["level"] == 2 and s["next_level_in"] == 2


def test_stats_need_login(client):
    assert client.get("/api/stats").status_code == 401


def test_stats_are_per_user(client, auth, planned, fire, signup):
    finished(client, auth, fire, planned["id"])
    token = signup("bo@example.com", "correct-horse", "Bo").get_json()["access_token"]
    other = stats(client, {"Authorization": f"Bearer {token}"})
    assert other["interviews"] == 0
