"""Reverse mode: the user interviews an AI candidate with a hidden profile."""

from app.extensions import db
from app.models import Session


def start(client, auth, docs, **extra):
    return client.post(
        "/api/reverse", json={"jd_id": docs["jd_id"], **extra}, headers=auth
    )


def test_candidate_is_created_with_the_profile_hidden(client, auth, docs, fire):
    r = start(client, auth, docs, profile="exaggerating")
    assert r.status_code == 201, r.get_json()
    v = r.get_json()["reverse"]
    assert v["candidate"] == {
        "name": "Sam",
        "headline": "Backend engineer, 4 years, payments",
        "resume": ["Led the payments API rewrite", "Cut errors by 90%"],
    }
    assert v["reveal"] is None
    assert "exaggerat" not in str(v).lower() and "Joined the rewrite late" not in str(v)
    prompt = next(
        c["prompt"]
        for c in fire.calls
        if "Create a realistic job candidate" in c["prompt"]
    )
    assert "Candidate type (hidden from the user): exaggerating" in prompt


def test_ask_then_decide_reveals_profile_and_feedback(client, auth, docs, fire):
    sid = start(client, auth, docs, profile="exaggerating").get_json()["reverse"]["id"]
    r = client.post(
        f"/api/reverse/{sid}/ask",
        json={"text": "Tell me about the rewrite."},
        headers=auth,
    )
    v = r.get_json()["reverse"]
    assert v["transcript"] == [
        {
            "question": "Tell me about the rewrite.",
            "answer": "I led the payments API rewrite and cut errors a lot.",
            "input_mode": "text",
        }
    ]
    prompt = fire.calls[-1]["prompt"]
    assert (
        "Joined the rewrite late" in prompt and "Tell me about the rewrite." in prompt
    )

    r = client.post(
        f"/api/reverse/{sid}/decide",
        json={"decision": "hire", "reasons": "Strong leader."},
        headers=auth,
    )
    v = r.get_json()["reverse"]
    assert v["status"] == "completed"
    assert v["reveal"]["profile"] == "exaggerating"
    assert v["reveal"]["hidden"]["exaggerations"] == [
        "Did not lead the rewrite; a teammate did"
    ]
    result = v["reveal"]["result"]
    assert result["decision_matches"] is False and result["expected"] == "no_hire"
    assert result["missed_signals"] == ["Never asked who led the rewrite."]
    assert (
        client.post(
            f"/api/reverse/{sid}/ask", json={"text": "One more?"}, headers=auth
        ).status_code
        == 409
    )


def test_average_candidates_can_go_either_way(client, auth, docs, fire):
    sid = start(client, auth, docs, profile="average").get_json()["reverse"]["id"]
    client.post(f"/api/reverse/{sid}/ask", json={"text": "Why this job?"}, headers=auth)
    r = client.post(
        f"/api/reverse/{sid}/decide",
        json={"decision": "no_hire", "reasons": "Too vague."},
        headers=auth,
    )
    assert r.get_json()["reverse"]["reveal"]["result"]["decision_matches"] is True


def test_decide_needs_a_question_and_limits(client, auth, docs, fire):
    sid = start(client, auth, docs).get_json()["reverse"]["id"]
    r = client.post(
        f"/api/reverse/{sid}/decide",
        json={"decision": "hire", "reasons": "Seems fine."},
        headers=auth,
    )
    assert r.status_code == 409
    from app.services import reverse

    reverse.MAX_QUESTIONS, old = 1, reverse.MAX_QUESTIONS
    try:
        client.post(f"/api/reverse/{sid}/ask", json={"text": "First?"}, headers=auth)
        r = client.post(
            f"/api/reverse/{sid}/ask", json={"text": "Second?"}, headers=auth
        )
        assert r.status_code == 409 and "decision" in r.get_json()["error"]
    finally:
        reverse.MAX_QUESTIONS = old


def test_surprise_picks_a_real_profile(client, auth, docs, fire):
    sid = start(client, auth, docs).get_json()["reverse"]["id"]
    profile = db.session.get(Session, sid).plan_json["reverse"]["profile"]
    assert profile in ("strong", "average", "weak", "exaggerating")


def test_normal_interview_routes_refuse_reverse_sessions(client, auth, docs, fire):
    sid = start(client, auth, docs).get_json()["reverse"]["id"]
    for path in ("turns", "hint", "skip", "pause", "report", "start"):
        r = client.post(
            f"/api/sessions/{sid}/{path}", json={"text": "hi"}, headers=auth
        )
        assert r.status_code == 409, path
    assert client.get("/api/stats", headers=auth).get_json()["stats"]["interviews"] == 0


def test_ownership(client, auth, docs, fire, signup):
    sid = start(client, auth, docs).get_json()["reverse"]["id"]
    token = signup("bo@example.com", "correct-horse", "Bo").get_json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/reverse/{sid}", headers=other).status_code == 404
    assert (
        client.post(
            "/api/reverse", json={"jd_id": docs["jd_id"]}, headers=other
        ).status_code
        == 404
    )
