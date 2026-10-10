"""Story bank: extraction after each report, merging, editing, coverage, suggestions."""

import re

from app.extensions import db
from app.models import Report, Story
from app.services.fire import FireError

from tests.test_modules import SALES_ANALYSIS, SALES_PLAN, create
from tests.test_reports import build
from tests.test_sessions import answer, started

ETL = (
    "Reporting queries were slowing our API, so I moved them to a nightly ETL job "
    "and p95 latency dropped from 1.8 seconds to 300 milliseconds."
)
MENTOR = (
    "I mentored two junior engineers with weekly pairing on real tickets, and both "
    "joined the on-call rotation within three months."
)


def ids(prompt: str) -> list[int]:
    return [int(i) for i in re.findall(r'"answer_id": (\d+)', prompt)]


def interview(client, auth, sid, *answers):
    started(client, auth, sid)
    for text in answers:
        answer(client, auth, sid, text)
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    return build(client, auth, sid).get_json()["report"]


def etl_story(prompt, **extra):
    return {
        "stories": [
            {
                "title": "Cut API latency with a nightly ETL",
                "situation": "Reporting queries were slowing our API",
                "task": None,
                "action": "I moved them to a nightly ETL job",
                # "dashboard" and "40%" were never said: dropped to a gap.
                "result": "p95 latency dropped 40% and I built a dashboard",
                "competencies": ["SQL Proficiency", "Problem solving"],
                "answer_ids": ids(prompt)[:1],
                **extra,
            }
        ]
    }


def test_stories_are_extracted_from_the_answers_after_the_report(
    client, auth, planned, fire
):
    fire.stories = [etl_story]
    interview(client, auth, planned["id"], ETL, MENTOR)
    prompt = next(
        c["prompt"] for c in fire.calls if "reusable interview stories" in c["prompt"]
    )
    assert ETL in prompt and "Never add details" in prompt

    body = client.get("/api/stories", headers=auth).get_json()
    [story] = body["stories"]
    assert story["title"] == "Cut API latency with a nightly ETL"
    assert story["star"] == {
        "situation": "Reporting queries were slowing our API",
        "task": None,
        "action": "I moved them to a nightly ETL job",
        "result": None,
    }
    assert story["missing"] == ["task", "result"]
    assert story["competencies"] == ["SQL Proficiency", "Problem solving"]
    assert story["strength"] is not None
    assert story["sources"][0]["question"]
    gaps = body["coverage"]["gaps"]
    assert "Conflict" in gaps and "Problem solving" not in gaps


def test_hypotheticals_and_opinions_are_not_stories(client, auth, planned, fire):
    fire.stories = [
        lambda p: {
            "stories": [
                {
                    "title": "Rate limiter",
                    "action": "I'd use a token bucket in Redis",
                    "answer_ids": ids(p)[:1],
                },
                {"title": "Teamwork", "action": None, "answer_ids": ids(p)[:1]},
                {
                    "title": "Made up",
                    "action": "I led a migration",
                    "answer_ids": [999999],
                },
            ]
        }
    ]
    interview(
        client,
        auth,
        planned["id"],
        "I'd use a token bucket per API key in Redis with a Lua script.",
        MENTOR,
    )
    assert client.get("/api/stories", headers=auth).get_json()["stories"] == []


def test_same_experience_is_merged_keeping_the_stronger_telling(
    client, auth, docs, planned, fire
):
    fire.stories = [etl_story]
    interview(client, auth, planned["id"], ETL, MENTOR)
    first = db.session.scalar(db.select(Story))
    first.strength = 1.0  # the first telling was weak
    db.session.commit()

    sid = client.post(
        "/api/sessions", json={**docs, "duration_min": 10}, headers=auth
    ).get_json()["session"]["id"]
    fire.stories = [
        lambda p: etl_story(p, title="Moved reports to a nightly ETL", same_as=first.id)
    ]
    interview(client, auth, sid, ETL, MENTOR)
    [story] = client.get("/api/stories", headers=auth).get_json()["stories"]
    assert story["title"] == "Moved reports to a nightly ETL"  # the stronger telling
    assert len(story["sources"]) == 2


def test_edits_are_kept_and_never_overwritten(client, auth, docs, planned, fire):
    fire.stories = [etl_story]
    interview(client, auth, planned["id"], ETL, MENTOR)
    story = client.get("/api/stories", headers=auth).get_json()["stories"][0]
    r = client.put(
        f"/api/stories/{story['id']}",
        json={
            "title": "My ETL story",
            "result": "Latency fell to 300 ms.",
            "competencies": ["Ownership"],
        },
        headers=auth,
    )
    assert r.status_code == 200 and r.get_json()["story"]["user_edited"] is True

    db.session.get(Story, story["id"]).strength = 0.5
    db.session.commit()
    sid = client.post(
        "/api/sessions", json={**docs, "duration_min": 10}, headers=auth
    ).get_json()["session"]["id"]
    fire.stories = [lambda p: etl_story(p, title="Another title", same_as=story["id"])]
    interview(client, auth, sid, ETL, MENTOR)
    [after] = client.get("/api/stories", headers=auth).get_json()["stories"]
    assert after["title"] == "My ETL story"
    assert after["star"]["result"] == "Latency fell to 300 ms."
    assert "Ownership" in after["competencies"]


def test_delete_and_ownership(client, auth, planned, fire, signup):
    fire.stories = [etl_story]
    interview(client, auth, planned["id"], ETL, MENTOR)
    sid = client.get("/api/stories", headers=auth).get_json()["stories"][0]["id"]
    token = signup("bo@example.com", "correct-horse", "Bo").get_json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.delete(f"/api/stories/{sid}", headers=other).status_code == 404
    assert (
        client.put(
            f"/api/stories/{sid}", json={"title": "x"}, headers=other
        ).status_code
        == 404
    )
    assert client.delete(f"/api/stories/{sid}", headers=auth).status_code == 200
    assert client.get("/api/stories", headers=auth).get_json()["stories"] == []


def test_suggests_stories_that_fit_a_job(client, auth, docs, planned, fire):
    fire.stories = [lambda p: etl_story(p, competencies=["Databases"])]
    interview(client, auth, planned["id"], ETL, MENTOR)
    r = client.get(
        f"/api/stories/suggest?jd_id={docs['jd_id']}", headers=auth
    ).get_json()
    assert r["stories"][0]["title"] == "Cut API latency with a nightly ETL"
    assert r["stories"][0]["fits"] == ["Databases"]


def test_extraction_runs_once_and_never_fails_the_report(client, auth, planned, fire):
    sid = planned["id"]
    fire.stories = [FireError("down")]
    report = interview(client, auth, sid, ETL, MENTOR)
    assert report["status"] == "ready"
    assert db.session.scalar(db.select(Report)).stories_at is None

    build(client, auth, sid)  # the report is re-requested: extraction is retried once
    calls = [c for c in fire.calls if "reusable interview stories" in c["prompt"]]
    assert len(calls) == 2
    build(client, auth, sid)
    assert (
        len([c for c in fire.calls if "reusable interview stories" in c["prompt"]]) == 2
    )


def test_roleplay_and_tiny_sessions_cost_nothing(client, auth, docs, fire):
    fire.analysis = SALES_ANALYSIS
    fire.plan = {**SALES_PLAN, "sections": [SALES_PLAN["sections"][1]]}
    sid = create(client, auth, docs).get_json()["session"]["id"]
    fire.turns = [{"action": "follow_up", "message": "Fine."}]
    interview(
        client,
        auth,
        sid,
        "I hear you on price, what does the current process cost you?",
    )
    assert not any("reusable interview stories" in c["prompt"] for c in fire.calls)
