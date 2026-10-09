from datetime import timedelta

import pytest

from app.extensions import db
from app.models import Answer, JdAnalysis, Question, Session, UsageLimit
from app.services.limits import today

from tests.conftest import RESUME


def started(client, auth, session_id):
    res = client.post(f"/api/sessions/{session_id}/start", headers=auth)
    assert res.status_code == 200, res.get_json()
    return res.get_json()["session"]


def answer(client, auth, session_id, text="My answer.", duration_ms=30_000):
    return client.post(
        f"/api/sessions/{session_id}/turns",
        json={"text": text, "duration_ms": duration_ms},
        headers=auth,
    )


def test_create_builds_plan_and_rubric(planned, fire):
    assert fire.kinds() == ["analysis", "plan", "rubric"]
    assert planned["status"] == "planned"
    assert planned["role_title"] == "Backend Engineer"
    sections = planned["plan"]["sections"]
    assert sum(s["minutes"] for s in sections) == 10  # 3 + 5 scaled to 10
    assert sections[1]["questions"][0] == "How would you design a rate limiter?"
    assert planned["plan"]["reserve"][0]["section"] == "Technical"
    weights = [c["weight"] for c in planned["rubric"]["criteria"]]
    assert sum(weights) == pytest.approx(1, abs=0.01)
    assert RESUME in fire.calls[1]["prompt"]


def test_jd_analysis_is_cached(client, auth, docs, planned, fire):
    client.post("/api/sessions", json={**docs, "duration_min": 10}, headers=auth)
    assert fire.kinds() == ["analysis", "plan", "rubric", "plan", "rubric"]
    assert JdAnalysis.query.count() == 1


def test_create_validation(client, auth, docs):
    bad = client.post("/api/sessions", json={**docs, "duration_min": 90}, headers=auth)
    assert bad.status_code == 400
    swapped = {
        "resume_id": docs["jd_id"],
        "jd_id": docs["resume_id"],
        "duration_min": 10,
    }
    assert client.post("/api/sessions", json=swapped, headers=auth).status_code == 404


def test_edit_plan(client, auth, planned):
    url = f"/api/sessions/{planned['id']}/plan"
    plan = {
        "sections": [
            {"name": "Intro", "minutes": 4, "questions": ["Tell me about yourself."]},
            {"name": "Deep dive", "minutes": 5, "questions": ["Why MySQL?", "  "]},
        ]
    }
    res = client.put(url, json=plan, headers=auth)
    assert res.status_code == 400 and "add up to 10" in res.get_json()["error"]

    plan["sections"][1]["minutes"] = 6
    res = client.put(url, json=plan, headers=auth)
    assert res.status_code == 200
    got = res.get_json()["session"]["plan"]
    assert [s["questions"] for s in got["sections"]] == [
        ["Tell me about yourself."],
        ["Why MySQL?"],
    ]
    assert got["reserve"] == []


def test_full_interview(client, auth, planned, fire):
    sid = planned["id"]
    s = started(client, auth, sid)
    first = s["transcript"][0]["interviewer"]
    assert first.startswith("Hi Ada") and "Walk me through your Acme project." in first
    assert s["timer"]["total_sec"] == 600 and s["timer"]["section"] == "Background"

    fire.turns = [
        {"action": "follow_up", "message": "What was your specific part in that?"},
        {
            "action": "next_question",
            "message": "Thanks. How would you design a rate limiter?",
        },
        {"action": "next_question", "message": "Okay. How do you index a slow query?"},
        {"action": "bonus", "message": "We have time: what is your favorite database?"},
        {"action": "wrap_up", "message": "Thanks, that's all from me."},
    ]
    actions = []
    for _ in range(5):
        res = answer(client, auth, sid)
        assert res.status_code == 200, res.get_json()
        actions.append(res.get_json()["turn"]["action"])
    assert actions == [
        "follow_up",
        "next_question",
        "next_question",
        "bonus",
        "wrap_up",
    ]

    session = res.get_json()["session"]
    assert session["status"] == "completed"
    transcript = session["transcript"]
    assert [t["is_follow_up"] for t in transcript] == [False, True, False, False, False]
    assert transcript[-1]["is_bonus"] and all(
        t["answer"] == "My answer." for t in transcript
    )
    assert Answer.query.count() == 5
    assert answer(client, auth, sid).status_code == 409

    # Turn prompts carry the clock and only the allowed moves.
    turn_prompt = fire.calls[3]["prompt"]
    assert "Time left in the interview: about 10 minutes" in turn_prompt
    assert '"follow_up": null' in turn_prompt
    assert '"next_question": "How would you design a rate limiter?"' in turn_prompt


def test_disallowed_move_falls_back_to_plan(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    fire.turns = [{"action": "bonus", "message": "Off-plan question"}]
    turn = answer(client, auth, sid).get_json()["turn"]
    assert turn == {
        "action": "next_question",
        "message": "Thank you. Next question: How would you design a rate limiter?",
    }


def test_out_of_time_wraps_up_without_fire(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    session = db.session.get(Session, sid)
    session.started_at -= timedelta(minutes=10)
    db.session.commit()
    calls_before = len(fire.calls)
    turn = answer(client, auth, sid).get_json()["turn"]
    assert turn["action"] == "wrap_up" and "all the time we have" in turn["message"]
    assert len(fire.calls) == calls_before


def test_section_over_time_skips_ahead(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    q = Question.query.filter(Question.asked_at.is_not(None)).one()
    q.asked_at -= timedelta(minutes=5)  # Background section (3 min) has run out
    db.session.get(Session, sid).started_at -= timedelta(minutes=5)
    db.session.commit()
    answer(client, auth, sid)
    prompt = fire.calls[-1]["prompt"]
    assert '"follow_up": null' not in prompt and "new part" in prompt


def test_end_early(client, auth, planned):
    sid = planned["id"]
    started(client, auth, sid)
    res = client.post(f"/api/sessions/{sid}/end", headers=auth)
    assert res.get_json()["session"]["status"] == "completed"


def test_start_counts_minutes_and_enforces_daily_cap(app, client, auth, docs, planned):
    started(client, auth, planned["id"])
    assert UsageLimit.query.one().minutes_used == 10
    app.config["DAILY_INTERVIEW_MINUTES"] = 15
    res = client.post("/api/sessions", json={**docs, "duration_min": 10}, headers=auth)
    assert res.status_code == 429 and "5 left" in res.get_json()["error"]


def test_monthly_budget_pauses_new_sessions(app, client, auth, docs, fire):
    db.session.add(UsageLimit(user_id=1, date=today(), fire_spend_usd=1.0))
    db.session.commit()
    res = client.post("/api/sessions", json={**docs, "duration_min": 10}, headers=auth)
    assert res.status_code == 429 and "budget" in res.get_json()["error"]
    assert fire.calls == []


def test_daily_plan_cap(app, client, auth, docs):
    app.config["DAILY_PLANS"] = 1
    assert (
        client.post(
            "/api/sessions", json={**docs, "duration_min": 10}, headers=auth
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/sessions", json={**docs, "duration_min": 10}, headers=auth
        ).status_code
        == 429
    )


def test_sessions_are_private(client, auth, planned, signup):
    other = signup(email="bob@example.com").get_json()["access_token"]
    headers = {"Authorization": f"Bearer {other}"}
    assert (
        client.get(f"/api/sessions/{planned['id']}", headers=headers).status_code == 404
    )
    assert (
        client.post(f"/api/sessions/{planned['id']}/start", headers=headers).status_code
        == 404
    )


def test_fire_errors_reach_the_user(client, auth, planned, fire):
    from app.services.fire import FireError

    started(client, auth, planned["id"])

    def broken(*args, **kwargs):
        raise FireError("The AI service is busy; please wait a moment", 429)

    fire.chat = broken
    res = answer(client, auth, planned["id"])
    assert res.status_code == 429 and "busy" in res.get_json()["error"]
    assert Answer.query.count() == 0  # nothing half-saved; the user can resend


@pytest.mark.parametrize(
    "said,expected",
    [
        (
            "Thanks for that insight. How did you optimize the queries?",
            "Thanks. How did you optimize the queries?",
        ),
        (
            "That sounds like a solid implementation! Can you explain the indexes?",
            "Thanks. Can you explain the indexes?",
        ),
        (
            "Got it. I appreciate your thoughts on mentoring. However, how did you tune MySQL?",
            "Got it. How did you tune MySQL?",
        ),
        ("Great answer. Next: why MySQL?", "Thanks. Next: why MySQL?"),
        ("Okay. Tell me about a strong result you achieved.", None),
        (
            "Great. Give me an example of a solid design you shipped.",
            "Thanks. Give me an example of a solid design you shipped.",
        ),
        ("Okay. What was the most interesting bug you fixed?", None),
        ("Thanks. Tell me about a time you disagreed with a teammate.", None),
    ],
)
def test_interviewer_never_praises(said, expected):
    from app.services.interviewer import neutralize

    assert neutralize(said) == (expected or said)


def test_praise_is_removed_from_live_turns(client, auth, planned, fire):
    started(client, auth, planned["id"])
    fire.turns = [
        {"action": "follow_up", "message": "Impressive work! What was your role?"}
    ]
    turn = answer(client, auth, planned["id"]).get_json()["turn"]
    assert turn["message"] == "Thanks. What was your role?"
