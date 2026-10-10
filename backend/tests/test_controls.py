"""Hint, skip, pause and resume during the interview (docs/INTERVIEWER_RULES.md, T-40)."""

from datetime import timedelta

from app.extensions import db
from app.models import Session
from app.services.interviewer import INVITE, SKIP_ACK

from tests.fakes import PLAN
from tests.test_reports import build
from tests.test_sessions import answer, started


def post(client, auth, sid, action):
    return client.post(f"/api/sessions/{sid}/{action}", headers=auth)


def test_hint_is_given_once_and_noted_when_scoring(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    r = post(client, auth, sid, "hint")
    assert r.status_code == 200
    assert r.get_json()["hint"] == "Think about where the requests are counted."
    assert "asked for a hint" in fire.calls[-1]["prompt"]
    assert r.get_json()["session"]["transcript"][0]["hint"].startswith("Think about")

    calls = len(fire.calls)
    assert post(client, auth, sid, "hint").get_json()["hint"].startswith("Think")
    assert len(fire.calls) == calls  # the same hint again, no new Fire call

    answer(client, auth, sid, "I'd count requests per key in Redis with a TTL.")
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    build(client, auth, sid)
    score = next(c["prompt"] for c in fire.calls if c["prompt"].startswith("Score one"))
    assert '"hint": "Think about where the requests are counted."' in score


def test_skip_moves_on_without_fire_and_lists_the_question(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    calls = len(fire.calls)
    r = post(client, auth, sid, "skip").get_json()
    second = PLAN["sections"][1]["questions"][0]
    assert r["turn"]["message"] == f"{SKIP_ACK} {second}"
    assert len(fire.calls) == calls

    answer(client, auth, sid, "I'd use a token bucket per API key in Redis with Lua.")
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    report = build(client, auth, sid).get_json()["report"]
    skipped = report["unanswered"][0]
    assert skipped["text"] == PLAN["sections"][0]["questions"][0] and skipped["asked"]


def test_skipping_the_last_question_invites_questions(app, client, auth, planned, fire):
    app.config["CANDIDATE_QUESTIONS"] = True
    sid = planned["id"]
    started(client, auth, sid)
    actions = [post(client, auth, sid, "skip").get_json()["turn"]["action"]]
    while actions[-1] in ("next_question", "bonus"):
        r = post(client, auth, sid, "skip").get_json()
        actions.append(r["turn"]["action"])
    assert actions == ["next_question", "next_question", "bonus", "your_questions"]
    assert r["turn"]["message"] == f"{SKIP_ACK} {INVITE}"
    r = post(client, auth, sid, "skip").get_json()  # no questions either
    assert r["turn"]["action"] == "wrap_up" and r["session"]["status"] == "completed"


def test_pause_stops_the_clock_and_blocks_answers(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    s = post(client, auth, sid, "pause").get_json()["session"]
    assert s["timer"]["paused"] is True
    assert answer(client, auth, sid).status_code == 409
    assert post(client, auth, sid, "hint").status_code == 409
    assert post(client, auth, sid, "skip").status_code == 409

    # Five minutes pass while paused: none of it counts.
    session = db.session.get(Session, sid)
    session.started_at -= timedelta(minutes=5)
    start, _ = session.pauses_json[0]
    from datetime import datetime

    moved = (datetime.fromisoformat(start) - timedelta(minutes=5)).isoformat()
    session.pauses_json = [[moved, None]]
    db.session.commit()
    s = post(client, auth, sid, "resume").get_json()["session"]
    assert s["timer"]["paused"] is False
    assert s["timer"]["elapsed_sec"] < 5
    assert (
        answer(client, auth, sid, "An answer with enough words in it.").status_code
        == 200
    )


def test_controls_need_a_live_interview(client, auth, planned):
    sid = planned["id"]
    for action in ("hint", "skip", "pause", "resume"):
        assert post(client, auth, sid, action).status_code == 409
