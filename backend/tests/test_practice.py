"""Question bank with spaced repetition, weak-spot interviews and weekly goals."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models import QuestionBankItem, Session
from app.models.base import utcnow
from app.services import practice
from app.services.fire import FireError

from tests.fakes import PLAN
from tests.test_modules import SALES_ANALYSIS, SALES_PLAN, create
from tests.test_reports import SCORE_ALL_FIVE, build, finished, retry
from tests.test_sessions import answer, started


def scored(score, criteria=None):
    return SimpleNamespace(
        score=score,
        rubric_scores_json={
            "criteria": criteria or [{"name": "API design", "kind": "role", "score": 2}]
        },
    )


def test_missed_questions_join_the_bank_after_the_report(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)  # every answer scores 3.7 with the fake scorer
    build(client, auth, sid)
    q = client.get("/api/practice", headers=auth).get_json()["practice"]
    assert q["due"] == [] and q["mastered"] == 0
    texts = [i["question"] for i in q["upcoming"]]
    assert texts == [
        PLAN["sections"][0]["questions"][0],
        PLAN["sections"][1]["questions"][0],
    ]
    item = db.session.scalar(db.select(QuestionBankItem))
    assert item.interval_days == 7  # 3.7: back in a week
    assert item.competency == "API design"


def test_spaced_repetition_schedule(app, client, auth, planned):
    session = db.session.get(Session, planned["id"])
    item = practice.review(
        1, session, "Design a cache.", "Technical", "technical", scored(2.0)
    )
    assert item.interval_days == 1
    practice.review(
        1, session, "design a CACHE. ", "Technical", "technical", scored(4.2)
    )
    assert item.reviews == 1 and item.interval_days == 7 and item.mastered_at is None
    practice.review(
        1, session, "Design a cache.", "Technical", "technical", scored(3.0)
    )
    assert item.reviews == 0 and item.interval_days == 3  # missed again: start over
    practice.review(
        1, session, "Design a cache.", "Technical", "technical", scored(4.5)
    )
    practice.review(
        1, session, "Design a cache.", "Technical", "technical", scored(4.0)
    )
    assert item.mastered_at is not None and item.next_review_at is None
    assert (
        practice.review(1, session, "Explain HTTP.", "T", "technical", scored(4.4))
        is None
    )


def test_weak_spot_interview_from_due_questions(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    for item in db.session.scalars(db.select(QuestionBankItem)):
        item.next_review_at = utcnow() - timedelta(hours=1)
    db.session.commit()
    calls = len(fire.calls)

    r = client.post("/api/sessions/practice", json={"duration_min": 10}, headers=auth)
    assert r.status_code == 201, r.get_json()
    s = r.get_json()["session"]
    assert len(fire.calls) == calls  # no Fire call to plan it
    assert s["plan"]["sections"][0]["name"] == "Weak spots"
    assert [q for q in s["plan"]["sections"][0]["questions"]] == [
        PLAN["sections"][0]["questions"][0],
        PLAN["sections"][1]["questions"][0],
    ]
    source = db.session.get(Session, sid)
    practice_session = db.session.get(Session, s["id"])
    assert practice_session.rubric_json == source.rubric_json
    assert practice_session.jd_id == source.jd_id

    # Practicing them updates the bank once the report is ready.
    fire.scores = [SCORE_ALL_FIVE, SCORE_ALL_FIVE]
    started(client, auth, s["id"])
    fire.turns = [{"action": "next_question", "message": "Next."}]
    for _ in range(2):
        answer(client, auth, s["id"], "A full answer with a clear result and numbers.")
    client.post(f"/api/sessions/{s['id']}/end", headers=auth)
    build(client, auth, s["id"])
    items = db.session.scalars(db.select(QuestionBankItem)).all()
    assert {i.reviews for i in items} == {1}


def test_nothing_to_practice_yet(client, auth):
    r = client.post("/api/sessions/practice", json={}, headers=auth)
    assert r.status_code == 404 and "Nothing to practice" in r.get_json()["error"]


def test_try_again_counts_as_a_review(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    qid = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()["report"][
        "questions"
    ][0]["question_id"]
    fire.scores = [SCORE_ALL_FIVE]
    retry(client, auth, sid, qid)
    item = db.session.scalar(
        db.select(QuestionBankItem).filter_by(
            question_text=PLAN["sections"][0]["questions"][0]
        )
    )
    assert item.reviews == 1 and item.interval_days == 14


def test_report_rerun_does_not_review_twice(client, auth, planned, fire):
    sid = planned["id"]
    fire.stories = [FireError("down")]  # the re-request retries only the story bank
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    build(client, auth, sid)
    item = db.session.scalar(db.select(QuestionBankItem))
    assert item.reviews == 0 and item.interval_days == 7


def test_roleplay_openers_are_not_banked(client, auth, docs, fire):
    fire.analysis = SALES_ANALYSIS
    fire.plan = {**SALES_PLAN, "sections": [SALES_PLAN["sections"][1]]}
    sid = create(client, auth, docs).get_json()["session"]["id"]
    started(client, auth, sid)
    answer(
        client,
        auth,
        sid,
        "I hear you on price; what does the manual process cost your team?",
    )
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    build(client, auth, sid)
    assert db.session.scalar(db.select(QuestionBankItem)) is None


def test_weekly_goal_and_practice_counts_in_stats(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    s = client.get("/api/stats", headers=auth).get_json()["stats"]
    assert s["goal"] == {"weekly": 3, "done_this_week": 1}
    assert s["practice"] == {"due": 0, "upcoming": 2, "mastered": 0}
    r = client.put("/api/stats/goal", json={"weekly_goal": 5}, headers=auth)
    assert r.get_json()["stats"]["goal"]["weekly"] == 5
    assert (
        client.put("/api/stats/goal", json={"weekly_goal": 0}, headers=auth).status_code
        == 400
    )


def test_skill_change_since_the_first_interview(client, auth, docs, planned, fire):
    finished(client, auth, fire, planned["id"])
    build(client, auth, planned["id"])
    other = client.post(
        "/api/sessions", json={**docs, "duration_min": 10}, headers=auth
    ).get_json()["session"]["id"]
    fire.scores = [SCORE_ALL_FIVE]
    started(client, auth, other)
    answer(
        client, auth, other, "A full answer with a clear result and real numbers in it."
    )
    client.post(f"/api/sessions/{other}/end", headers=auth)
    build(client, auth, other)
    skills = {
        k["name"]: k
        for k in client.get("/api/stats", headers=auth).get_json()["stats"]["skills"]
    }
    assert skills["Structure"]["change"] == pytest.approx(2.0)  # 3 → 5
