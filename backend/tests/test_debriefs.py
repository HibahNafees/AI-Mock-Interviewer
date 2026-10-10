"""Post-interview debrief: recall-only, scored, next round predicted and practiced."""

from app.extensions import db
from app.models import Debrief, QuestionBankItem, Session
from app.services.debriefs import DEFAULT_RUBRIC
from app.services.fire import FireError

ITEMS = [
    {
        "question": "Tell me about yourself.",
        "answer": "I'm a backend engineer at Acme; I built the refunds API in Flask and own its MySQL schema.",
    },
    {
        "question": "How do you handle a slow query?",
        "answer": "I'd run EXPLAIN, add a composite index, and check the slow query log afterwards.",
    },
]


def debrief(client, auth, **extra):
    return client.post(
        "/api/debriefs",
        json={
            "role": "Backend Engineer",
            "company": "Fintech Co",
            "round": "Phone screen",
            "items": ITEMS,
            **extra,
        },
        headers=auth,
    )


def test_recalled_interview_is_scored_like_a_report(client, auth, fire):
    r = debrief(client, auth)
    assert r.status_code == 201, r.get_json()
    d = r.get_json()["debrief"]
    session = db.session.get(Session, d["session_id"])
    assert session.mode == "debrief" and session.status == "completed"
    assert session.rubric_json == DEFAULT_RUBRIC  # no JD: no Fire call for a rubric
    report = client.get(
        f"/api/sessions/{d['session_id']}/report", headers=auth
    ).get_json()["report"]
    assert report["status"] == "ready"
    assert [q["text"] for q in report["questions"]] == [i["question"] for i in ITEMS]
    assert report["debrief"]["company"] == "Fintech Co"
    # Next round predicted once the report is ready; odd modules fall back.
    nxt = report["debrief"]["next_round"]
    assert [q["module"] for q in nxt] == ["technical", "behavioral", "behavioral"]
    prompt = next(c["prompt"] for c in fire.calls if "next round" in c["prompt"])
    assert "Phone screen" in prompt and "Fintech Co" in prompt
    # Real-interview questions they missed join the practice queue too.
    assert db.session.scalar(db.select(QuestionBankItem)) is not None


def test_practice_the_next_round(client, auth, fire):
    d = debrief(client, auth).get_json()["debrief"]
    calls = len(fire.calls)
    r = client.post(
        f"/api/debriefs/{d['id']}/practice", json={"duration_min": 10}, headers=auth
    )
    assert r.status_code == 201, r.get_json()
    s = r.get_json()["session"]
    assert len(fire.calls) == calls  # no Fire call to plan it
    sections = s["plan"]["sections"]
    assert [x["module"] for x in sections] == ["technical", "behavioral"]
    assert sum(x["minutes"] for x in sections) == 10
    assert "Walk me through a schema you designed." in sections[0]["questions"]
    assert s["status"] == "planned"


def test_prediction_failure_is_retried_on_request(client, auth, fire):
    fire.next_round = FireError("down")
    d = debrief(client, auth).get_json()["debrief"]
    assert db.session.get(Debrief, d["id"]).analysis_json is None
    r = client.post(f"/api/debriefs/{d['id']}/practice", json={}, headers=auth)
    assert r.status_code == 409
    fire.next_round = {
        "questions": [
            {"question": "Design a ledger.", "why": "payments", "module": "technical"}
        ]
    }
    r = client.post(f"/api/debriefs/{d['id']}/predict", headers=auth)
    assert r.get_json()["debrief"]["next_round"][0]["question"] == "Design a ledger."


def test_with_a_job_description_the_rubric_fits_the_job(client, auth, docs, fire):
    r = debrief(client, auth, jd_id=docs["jd_id"], resume_id=docs["resume_id"])
    session = db.session.get(Session, r.get_json()["debrief"]["session_id"])
    assert session.rubric_json != DEFAULT_RUBRIC
    assert session.jd_id == docs["jd_id"] and session.resume_id == docs["resume_id"]


def test_debriefs_are_not_counted_as_mock_interviews(client, auth, fire):
    debrief(client, auth)
    s = client.get("/api/stats", headers=auth).get_json()["stats"]
    assert s["interviews"] == 0 and s["history"] == []


def test_validation_and_ownership(client, auth, fire, signup):
    assert (
        client.post(
            "/api/debriefs", json={"role": "X", "items": []}, headers=auth
        ).status_code
        == 400
    )
    assert debrief(client, auth, jd_id=999).status_code == 404
    d = debrief(client, auth).get_json()["debrief"]
    token = signup("bo@example.com", "correct-horse", "Bo").get_json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert (
        client.post(f"/api/debriefs/{d['id']}/practice", headers=other).status_code
        == 404
    )
    assert client.delete(f"/api/debriefs/{d['id']}", headers=other).status_code == 404
    assert client.get("/api/debriefs", headers=other).get_json()["debriefs"] == []
    assert client.delete(f"/api/debriefs/{d['id']}", headers=auth).status_code == 200
    assert db.session.get(Session, d["session_id"]) is None


def test_spoken_recall_is_transcribed_not_stored(client, auth, fire):
    import io

    data = {"audio": (io.BytesIO(b"x" * 2000), "answer.webm", "audio/webm")}
    r = client.post(
        "/api/debriefs/transcribe",
        data=data,
        headers=auth,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200 and r.get_json()["text"]
    assert fire.audio  # sent to Fire for transcription only
