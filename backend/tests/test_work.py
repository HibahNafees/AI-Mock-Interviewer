"""Coding round and whiteboard: the code or sketch travels with the answer."""

from app.extensions import db
from app.models import Answer

from tests.fakes import PLAN
from tests.test_sessions import answer, started

CODE = {
    "kind": "code",
    "language": "python",
    "content": "def allow(user):\n    return bucket[user].take()",
}
SKETCH = {
    "kind": "whiteboard",
    "content": "Boxes: API, Redis\nArrows: API → Redis (count requests)",
}
CODING_PLAN = {
    "sections": [
        {
            "name": "Coding",
            "module": "coding",
            "minutes": 6,
            "questions": ["Write a function that rate-limits each user."],
        },
        {
            "name": "Design",
            "module": "system_design",
            "minutes": 4,
            "questions": ["Design a rate limiter for many servers."],
        },
    ],
    "reserve": [],
}


def coding_session(client, auth, docs, fire):
    fire.analysis = {
        **fire.analysis,
        "formats": [*fire.analysis["formats"], "system_design"],
    }
    fire.plan = CODING_PLAN
    r = client.post(
        "/api/sessions", json={**docs, "duration_min": 10}, headers=auth
    ).get_json()
    sid = r["session"]["id"]
    started(client, auth, sid)
    return r["session"], sid


def send(client, auth, sid, text, work=None):
    return client.post(
        f"/api/sessions/{sid}/turns",
        json={"text": text, "duration_ms": 30_000, **({"work": work} if work else {})},
        headers=auth,
    )


def test_coding_and_system_design_are_planned_with_their_guidance(
    client, auth, docs, fire
):
    session, _ = coding_session(client, auth, docs, fire)
    modules = [s["module"] for s in session["plan"]["sections"]]
    assert modules == ["coding", "system_design"]
    plan_prompt = next(
        c["prompt"] for c in fire.calls if "question plan" in c["prompt"]
    )
    assert "code editor" in plan_prompt or "programming problem" in plan_prompt


def test_code_reaches_the_interviewer_and_is_saved(client, auth, docs, fire):
    _, sid = coding_session(client, auth, docs, fire)
    fire.turns = [{"action": "follow_up", "message": "What about an empty bucket?"}]
    r = send(client, auth, sid, "I keep a token bucket per user.", CODE)
    assert r.status_code == 200, r.get_json()
    prompt = fire.calls[-1]["prompt"]
    assert "[Code in the editor (python)]" in prompt
    assert "bucket[user].take()" in prompt
    assert "arrives with each answer in a [Code in the editor] block" in prompt
    saved = db.session.scalar(db.select(Answer).order_by(Answer.id.desc()))
    assert saved.transcript == "I keep a token bucket per user."  # spoken words only
    assert saved.work_json == CODE
    shown = r.get_json()["session"]["transcript"][0]
    assert shown["work"] == CODE

    # The next turn's history still shows the earlier code.
    fire.turns = [{"action": "next_question", "message": "Now, the design."}]
    send(client, auth, sid, "It refills over time.")
    assert "bucket[user].take()" in fire.calls[-1]["prompt"]


def test_work_is_validated(client, auth, docs, fire):
    _, sid = coding_session(client, auth, docs, fire)
    r = send(client, auth, sid, "Here.", {"kind": "code", "content": "   "})
    assert r.status_code == 400
    r = send(client, auth, sid, "Here.", {"kind": "video", "content": "x"})
    assert r.status_code == 400
    r = send(client, auth, sid, "Here.", {**CODE, "language": "brainfuck"})
    assert r.status_code == 200
    assert db.session.scalar(db.select(Answer).order_by(Answer.id.desc())).work_json[
        "language"
    ] == ("plaintext")


def test_scorer_judges_the_code_and_the_sketch(app, client, auth, docs, fire):
    app.config["REPORTS_INLINE"] = True
    _, sid = coding_session(client, auth, docs, fire)
    fire.turns = [{"action": "next_question", "message": "Now, the design."}] * 2
    # A short spoken answer is still scored when the code carries it.
    send(client, auth, sid, "Here it is.", CODE)
    send(client, auth, sid, "Redis holds the counters.", SKETCH)
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    report = client.post(f"/api/sessions/{sid}/report", headers=auth).get_json()
    scores = [c["prompt"] for c in fire.calls if "Score one question" in c["prompt"]]
    assert len(scores) == 2
    assert "bucket[user].take()" in scores[0]
    assert "Judge the code shown" in scores[0]
    assert "[Whiteboard sketch, described as text]" in scores[1]
    assert "API → Redis" in scores[1]
    exchange = report["report"]["questions"][0]["exchange"][0]
    assert exchange["work"] == CODE and exchange["answer"] == "Here it is."


def test_plain_answers_have_no_work(client, auth, planned, fire):
    started(client, auth, planned["id"])
    answer(client, auth, planned["id"])
    assert db.session.scalar(db.select(Answer)).work_json is None
    assert PLAN["sections"][0]["module"] == "resume_deepdive"
