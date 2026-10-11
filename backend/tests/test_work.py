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
        "/api/sessions", json={**docs, "duration_min": 20}, headers=auth
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


# ---- body language ------------------------------------------------------------

STEADY = {
    "samples": 40,
    "face_pct": 95,
    "eye_contact_pct": 80,
    "upright_pct": 90,
    "fidget_pct": 10,
}


def test_body_language_numbers_are_saved_never_sent_to_fire(
    app, client, auth, planned, fire
):
    app.config["REPORTS_INLINE"] = True
    sid = planned["id"]
    started(client, auth, sid)
    looked_away = {**STEADY, "samples": 20, "eye_contact_pct": 20, "fidget_pct": 70}
    for body in (STEADY, looked_away):
        r = client.post(
            f"/api/sessions/{sid}/turns",
            json={
                "text": "I built the billing API.",
                "duration_ms": 30_000,
                "body": body,
            },
            headers=auth,
        )
        assert r.status_code == 200, r.get_json()
    saved = db.session.scalars(db.select(Answer).order_by(Answer.id)).all()
    assert saved[0].body_json == STEADY
    assert all("eye_contact" not in c["prompt"] for c in fire.calls)

    client.post(f"/api/sessions/{sid}/end", headers=auth)
    report = client.post(f"/api/sessions/{sid}/report", headers=auth).get_json()
    body = report["report"]["body_language"]
    # Weighted by how long the camera watched each answer.
    assert body["eye_contact_pct"] == 60 and body["fidget_pct"] == 30
    assert body["answers"] == 2
    assert any("hands" in t for t in body["tips"])
    assert all("eye_contact" not in c["prompt"] for c in fire.calls)


def test_body_language_is_optional_and_validated(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    bad = client.post(
        f"/api/sessions/{sid}/turns",
        json={"text": "Hi.", "body": {**STEADY, "eye_contact_pct": 140}},
        headers=auth,
    )
    assert bad.status_code == 400
    answer(client, auth, sid)
    assert db.session.scalar(db.select(Answer)).body_json is None


def test_off_topic_code_answer_gets_how_to_solve_not_a_story(
    app, client, auth, docs, fire
):
    # Live check (T-56): an off-topic coding answer got "[Describe one specific
    # time: the situation…]", a behavioral placeholder.
    from tests.fakes import SCORE

    app.config["REPORTS_INLINE"] = True
    _, sid = coding_session(client, auth, docs, fire)
    fire.turns = [{"action": "next_question", "message": "Now, the design."}]
    send(client, auth, sid, "I like working with databases a lot, honestly.", CODE)
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    off = {
        **SCORE,
        "criteria": [
            {"name": "API design", "score": 1},
            {"name": "Structure", "score": 2},
            {"name": "Clarity", "score": 2},
            {"name": "Relevance", "score": 1},
        ],
    }
    fire.scores = [off]
    report = client.post(f"/api/sessions/{sid}/report", headers=auth).get_json()
    stronger = report["report"]["questions"][0]["evaluation"]["stronger_version"]
    assert "complexity" in stronger and "specific time" not in stronger


# ---- hands-on choices (T-62, T-65) ---------------------------------------------


def test_software_roles_always_offer_coding_and_design(client, auth, docs, fire):
    fire.analysis = {
        **fire.analysis,
        "role_title": "Software Developer",
        "field": "software engineering",
        "formats": ["behavioral", "resume_deepdive", "technical"],
    }
    r = client.post(f"/api/documents/{docs['jd_id']}/analysis", headers=auth)
    names = [m["name"] for m in r.get_json()["modules"]]
    assert "coding" in names and "system_design" in names


def test_non_software_technical_roles_dont_get_coding(client, auth, docs, fire):
    fire.analysis = {
        **fire.analysis,
        "role_title": "Accountant",
        "field": "accounting",
        "formats": ["behavioral", "technical"],
    }
    r = client.post(f"/api/documents/{docs['jd_id']}/analysis", headers=auth)
    assert "coding" not in [m["name"] for m in r.get_json()["modules"]]


def two_problem_plan():
    return {
        "sections": [
            {
                "name": "Coding",
                "module": "coding",
                "minutes": 16,
                "questions": ["Reverse a list.", "Find duplicates."],
            },
            {
                "name": "Background",
                "module": "resume_deepdive",
                "minutes": 4,
                "questions": ["Walk me through Acme."],
            },
        ],
        "reserve": [],
    }


def test_asked_number_of_coding_problems_is_enforced(client, auth, docs, fire):
    # First reply has one problem; the retry has the two the candidate asked for.
    one = two_problem_plan()
    one["sections"][0]["questions"] = ["Reverse a list."]
    replies = [one, two_problem_plan()]
    plans = []

    real_chat = fire.chat

    def chat(messages, **kw):
        if "question plan" in messages[0]["content"]:
            plans.append(messages)
            fire.plan = replies[len(plans) - 1]
        return real_chat(messages, **kw)

    fire.chat = chat
    r = client.post(
        "/api/sessions",
        json={**docs, "duration_min": 20, "coding_problems": 2, "system_design": False},
        headers=auth,
    )
    assert r.status_code == 201, r.get_json()
    prompt = plans[0][0]["content"]
    assert "Use exactly 2 coding problem(s)" in prompt
    assert 'Don\'t use the "system_design" module.' in prompt
    assert len(plans) == 2 and "exactly 2 question(s)" in plans[1][-1]["content"]
    coding = [
        s
        for s in r.get_json()["session"]["plan"]["sections"]
        if s["module"] == "coding"
    ]
    assert len(coding[0]["questions"]) == 2


def test_coding_count_is_capped_by_the_length(client, auth, docs, fire):
    fire.plan = {
        "sections": [
            {
                "name": "Coding",
                "module": "coding",
                "minutes": 10,
                "questions": ["A.", "B."],
            }
        ],
        "reserve": [],
    }
    # 10 minutes keep 8 for coding: two problems at the 4-minute floor (T-85).
    r = client.post(
        "/api/sessions",
        json={**docs, "duration_min": 10, "coding_problems": 3},
        headers=auth,
    )
    assert r.status_code == 201, r.get_json()
    prompt = next(c["prompt"] for c in fire.calls if "question plan" in c["prompt"])
    assert "Use exactly 2 coding problem(s)" in prompt


def test_up_to_ten_coding_and_design_questions_can_be_chosen(client, auth, docs, fire):
    fire.analysis = {
        **fire.analysis,
        "formats": [*fire.analysis["formats"], "system_design"],
    }
    fire.plan = {
        "sections": [
            {
                "name": "Coding",
                "module": "coding",
                "minutes": 40,
                "questions": [f"Problem {i}." for i in range(10)],
            },
            {
                "name": "Design",
                "module": "system_design",
                "minutes": 20,
                "questions": ["Design A.", "Design B."],
            },
        ],
        "reserve": [],
    }
    r = client.post(
        "/api/sessions",
        json={
            **docs,
            "duration_min": 60,
            "coding_problems": 10,
            "system_design": 2,
        },
        headers=auth,
    )
    assert r.status_code == 201, r.get_json()
    prompt = next(c["prompt"] for c in fire.calls if "question plan" in c["prompt"])
    assert "Use exactly 10 coding problem(s)" in prompt
    assert "Use exactly 2 system design question(s)" in prompt
    sections = {s["module"]: s for s in r.get_json()["session"]["plan"]["sections"]}
    assert len(sections["coding"]["questions"]) == 10
    assert sections["coding"]["minutes"] >= 40
    assert sections["system_design"]["minutes"] >= 10
    too_many = client.post(
        "/api/sessions",
        json={**docs, "duration_min": 60, "coding_problems": 11},
        headers=auth,
    )
    assert too_many.status_code == 400


def test_run_output_goes_with_the_code(client, auth, docs, fire):
    _, sid = coding_session(client, auth, docs, fire)
    fire.turns = [{"action": "follow_up", "message": "Why a list?"}]
    work = {**CODE, "output": "[2, 4, 6]"}
    r = send(client, auth, sid, "Here is my function and what it printed.", work)
    assert r.status_code == 200, r.get_json()
    prompt = fire.calls[-1]["prompt"]
    assert "[Output when the candidate last ran it]\n[2, 4, 6]" in prompt
    saved = db.session.scalar(db.select(Answer).order_by(Answer.id.desc()))
    assert saved.work_json["output"] == "[2, 4, 6]"


def test_code_without_a_run_saves_no_output_key(client, auth, docs, fire):
    _, sid = coding_session(client, auth, docs, fire)
    fire.turns = [{"action": "follow_up", "message": "Walk me through it."}]
    send(client, auth, sid, "Here is my function.", CODE)
    saved = db.session.scalar(db.select(Answer).order_by(Answer.id.desc()))
    assert "output" not in saved.work_json
    assert "[Output when" not in fire.calls[-1]["prompt"]
