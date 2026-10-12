"""Pressure mode: levels, time limits, ease-off control, composure score."""


from app.extensions import db
from app.models import Report
from app.services.pressure import LEVEL_NOTES, RESPECT

from tests.fakes import PLAN
from tests.test_modules import SALES_ANALYSIS, SALES_PLAN, create
from tests.test_reports import build, finished
from tests.test_sessions import answer, started


def encoded(note: str) -> str:
    """Notes reach the prompt as plain lines under "Pressure interview" (T-96)."""
    return f"- {note}"


def pressured(client, auth, docs, level):
    r = create(client, auth, docs, pressure_level=level)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["session"]


def test_level_three_adds_time_limits_and_pushback(client, auth, docs, fire):
    s = pressured(client, auth, docs, 3)
    assert s["mode"] == "pressure"
    assert s["pressure"] == {
        "level": 3,
        "start_level": 3,
        "label": "60 s answers",
        "time_limit_sec": 60,
    }
    first = started(client, auth, s["id"])["transcript"][0]["interviewer"]
    assert first.endswith("You have 60 seconds for this one.")

    fire.turns = [{"action": "next_question", "message": "Okay."}]
    r = answer(
        client, auth, s["id"], "An answer about the billing API at Acme."
    ).get_json()
    prompt = next(
        c["prompt"]
        for c in reversed(fire.calls)
        if "live practice interview" in c["prompt"]
    )
    for n in (1, 2, 3):
        assert encoded(LEVEL_NOTES[n]) in prompt
    assert encoded(LEVEL_NOTES[4]) not in prompt
    assert RESPECT in prompt
    assert r["turn"]["message"].endswith("You have 60 seconds for this one.")


def test_level_one_is_skeptical_without_a_clock(client, auth, docs, fire):
    s = pressured(client, auth, docs, 1)
    assert s["pressure"]["time_limit_sec"] is None
    first = started(client, auth, s["id"])["transcript"][0]["interviewer"]
    assert "seconds" not in first


def test_pressure_can_be_lowered_or_stopped_never_raised(client, auth, docs, fire):
    s = pressured(client, auth, docs, 4)
    started(client, auth, s["id"])
    url = f"/api/sessions/{s['id']}/pressure"
    r = client.post(url, json={"level": 2}, headers=auth).get_json()["session"]
    assert r["pressure"]["level"] == 2 and r["pressure"]["time_limit_sec"] is None
    r = client.post(url, json={"level": 5}, headers=auth).get_json()["session"]
    assert r["pressure"]["level"] == 2  # can't be raised mid-interview
    r = client.post(url, json={"level": 0}, headers=auth).get_json()["session"]
    assert r["pressure"]["label"] == "Off"
    fire.turns = [{"action": "next_question", "message": "Okay."}]
    answer(client, auth, s["id"], "An answer about the billing API at Acme.")
    prompt = next(
        c["prompt"]
        for c in reversed(fire.calls)
        if "live practice interview" in c["prompt"]
    )
    assert LEVEL_NOTES[1] not in prompt and RESPECT not in prompt


def test_ease_pressure_only_in_pressure_interviews(client, auth, planned):
    started(client, auth, planned["id"])
    r = client.post(
        f"/api/sessions/{planned['id']}/pressure", json={"level": 0}, headers=auth
    )
    assert r.status_code == 409


def test_composure_compares_with_normal_interviews(client, auth, docs, planned, fire):
    finished(client, auth, fire, planned["id"])  # normal interview: 3.7 average
    build(client, auth, planned["id"])
    s = pressured(client, auth, docs, 2)
    finished(client, auth, fire, s["id"])
    report = build(client, auth, s["id"]).get_json()["report"]
    c = report["pressure"]["composure"]
    assert c["pct"] == 100 and c["baseline"] == 3.7 and c["same_job"] is True
    assert c["label"] == "Held up well under pressure"
    # Scoring never sees the pressure: same standards as a normal interview.
    scoring = [p["prompt"] for p in fire.calls if p["prompt"].startswith("Score one")]
    assert not any(LEVEL_NOTES[1] in p for p in scoring)

    db.session.scalar(db.select(Report).filter_by(session_id=s["id"])).overall_score = (
        2.5
    )
    db.session.commit()
    c = client.get(f"/api/sessions/{s['id']}/report", headers=auth).get_json()[
        "report"
    ]["pressure"]["composure"]
    assert c["pct"] == 68 and c["label"] == "Pressure noticeably affected your answers"


def test_composure_needs_a_normal_interview_first(client, auth, docs, fire):
    s = pressured(client, auth, docs, 2)
    finished(client, auth, fire, s["id"])
    c = build(client, auth, s["id"]).get_json()["report"]["pressure"]["composure"]
    assert c["pct"] is None and "normal interview" in c["label"]


def test_no_clock_inside_a_roleplay(client, auth, docs, fire):
    fire.analysis = SALES_ANALYSIS
    fire.plan = {**SALES_PLAN, "sections": [SALES_PLAN["sections"][1]]}
    s = pressured(client, auth, docs, 5)
    first = started(client, auth, s["id"])["transcript"][0]["interviewer"]
    assert "seconds" not in first


# ---- pressure questions in the plan, personas and difficulty (T-96, T-97) ----


def test_pressure_level_shapes_the_planned_questions(client, auth, docs, fire):
    pressured(client, auth, docs, 3)
    prompt = next(c["prompt"] for c in fire.calls if "question plan" in c["prompt"])
    assert "This is a pressure interview, level 3 of 5." in prompt
    assert "challenge a specific claim from the résumé" in prompt
    assert "tight constraints" in prompt and "Make most of them" not in prompt


def test_normal_plan_has_no_pressure_questions(client, auth, docs, fire):
    assert create(client, auth, docs).status_code == 201
    prompt = next(c["prompt"] for c in fire.calls if "question plan" in c["prompt"])
    assert "pressure interview" not in prompt


def turn_prompt(client, auth, docs, fire, **extra):
    r = create(client, auth, docs, **extra)
    assert r.status_code == 201, r.get_json()
    sid = r.get_json()["session"]["id"]
    started(client, auth, sid)
    fire.turns = [{"action": "follow_up", "message": "Great answer. What did you do?"}]
    turn = answer(client, auth, sid, "An answer about the billing API at Acme.")
    prompt = next(
        c["prompt"]
        for c in reversed(fire.calls)
        if "live practice interview" in c["prompt"]
    )
    return prompt, turn.get_json()["turn"]["message"]


def test_tough_interviewer_skips_thanks_and_probes(client, auth, docs, fire):
    prompt, said = turn_prompt(client, auth, docs, fire, persona="tough")
    assert "No pleasantries" in prompt and "Don't thank them" in prompt
    # The praise is dropped and no "Thanks." is put in its place.
    assert said == "What did you do?"


def test_friendly_interviewer_is_warm(client, auth, docs, fire):
    prompt, said = turn_prompt(client, auth, docs, fire, persona="friendly")
    assert (
        "warm and encouraging" in prompt and "Thanks for walking me through" in prompt
    )
    assert said == "Thanks. What did you do?"


def test_pressure_opens_like_tough_whatever_the_persona(client, auth, docs, fire):
    prompt, said = turn_prompt(
        client, auth, docs, fire, persona="friendly", pressure_level=2
    )
    assert "Don't thank them" in prompt and said == "What did you do?"


def test_difficulty_shapes_follow_ups(client, auth, docs, fire):
    prompt, _ = turn_prompt(client, auth, docs, fire, difficulty="senior")
    assert "Senior level: probe scope, trade-offs" in prompt
