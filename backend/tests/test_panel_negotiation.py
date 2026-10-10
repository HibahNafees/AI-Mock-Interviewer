"""Panel interviews (2–3 interviewers taking turns) and the negotiation role-play."""

from app.models import Session
from app.services import negotiation, panel

from tests.fakes import PLAN
from tests.test_sessions import answer, started

TERMS = {"offer": "$80,000 base", "target": "$92,000", "company": "Acme"}


def create(client, auth, docs, **extra):
    return client.post(
        "/api/sessions", json={**docs, "duration_min": 10, **extra}, headers=auth
    )


# ---- panel ------------------------------------------------------------------


def test_panel_gives_each_section_to_an_interviewer(client, auth, docs, fire):
    r = create(client, auth, docs, format="panel")
    assert r.status_code == 201, r.get_json()
    s = r.get_json()["session"]
    assert s["mode"] == "panel"
    assert [p["key"] for p in s["panel"]] == ["hm", "peer"]  # 10 min: two of them
    owners = {x["name"]: x["panelist"] for x in s["plan"]["sections"]}
    assert owners == {"Background": "hm", "Technical": "peer"}

    long = create(client, auth, docs, format="panel", duration_min=30).get_json()
    assert [p["key"] for p in long["session"]["panel"]] == ["hm", "peer", "hr"]


def test_panel_introduces_itself_and_hands_over(app, client, auth, docs, fire):
    app.config["ICEBREAKER"] = True
    sid = create(client, auth, docs, format="panel").get_json()["session"]["id"]
    first = started(client, auth, sid)["transcript"][0]["segments"]
    assert first == [{"who": "interviewer", "text": first[0]["text"], "panelist": "hm"}]
    assert "I'm Priya, the hiring manager, and with me is Marcus" in first[0]["text"]

    # Small talk → the hiring manager's résumé question.
    data = answer(client, auth, sid, "Doing well!").get_json()
    assert {s.get("panelist") for s in data["turn"]["segments"]} == {"hm"}

    # The hiring manager's section → the peer's technical question.
    fire.turns = [{"action": "next_question", "message": "Okay. Rate limiter time?"}]
    data = answer(client, auth, sid, "I built the billing API at Acme.").get_json()
    segs = data["turn"]["segments"]
    assert [(s["panelist"], s["text"]) for s in segs] == [
        ("hm", "Thanks. I'll hand over to Marcus now."),
        (
            "peer",
            "Hi, Marcus here, a senior colleague on the team. "
            "How would you design a rate limiter?",
        ),
    ]
    # The peer's follow-up prompt says who is speaking.
    fire.turns = [{"action": "follow_up", "message": "Where do you store counters?"}]
    data = answer(client, auth, sid, "A token bucket per user.").get_json()
    assert data["turn"]["segments"][0]["panelist"] == "peer"
    assert "You are Marcus, a senior colleague on the team" in fire.calls[-1]["prompt"]


def test_panel_wrap_up_is_the_hiring_managers(client, auth, docs, fire):
    fire.plan = {**PLAN, "sections": PLAN["sections"][1:], "reserve": []}
    sid = create(client, auth, docs, format="panel").get_json()["session"]["id"]
    s = started(client, auth, sid)
    segs = s["transcript"][0]["segments"]
    # The lead opens, then hands the first (technical) question to the peer.
    assert [x["panelist"] for x in segs] == ["hm", "peer"]
    assert segs[0]["text"].endswith("Let's begin. Marcus will start us off.")
    fire.turns = [{"action": "next_question", "message": "Next one."}] * 2
    answer(client, auth, sid)
    data = answer(client, auth, sid).get_json()
    assert data["turn"]["action"] == "wrap_up"
    assert {x["panelist"] for x in data["turn"]["segments"]} == {"hm"}


def test_panel_keeps_owners_when_the_plan_is_edited(client, auth, docs, fire):
    s = create(client, auth, docs, format="panel").get_json()["session"]
    plan = s["plan"]
    plan["sections"][0]["module"] = "technical"
    r = client.put(f"/api/sessions/{s['id']}/plan", json=plan, headers=auth)
    assert r.status_code == 200, r.get_json()
    owners = [x["panelist"] for x in r.get_json()["session"]["plan"]["sections"]]
    assert owners == ["peer", "peer"]


def test_pressure_is_only_for_standard_interviews(client, auth, docs, fire):
    r = create(client, auth, docs, format="panel", pressure_level=2)
    assert r.status_code == 400


def test_introductions_read_naturally():
    s = Session(mode="panel", duration_min=30, plan_json={})
    panel.assign(s)
    assert panel.introductions(s) == (
        "I'm Priya, the hiring manager, and with me are Marcus, a senior colleague "
        "on the team, and Elena, from the People team. We'll take turns asking "
        "questions."
    )


# ---- negotiation --------------------------------------------------------------


def test_negotiation_needs_no_plan_or_rubric_call(client, auth, docs, fire):
    r = create(client, auth, docs, format="negotiation", negotiation=TERMS)
    assert r.status_code == 201, r.get_json()
    s = r.get_json()["session"]
    assert fire.kinds() == ["analysis"]
    assert s["mode"] == "negotiation"
    assert s["negotiation"] == TERMS
    [section] = s["plan"]["sections"]
    assert section["module"] == "roleplay"
    assert "private" not in section["scenario"]  # the recruiter's room stays hidden
    assert "$80,000 base" in section["questions"][0]
    assert [c["name"] for c in s["rubric"]["criteria"]] == [
        "Anchoring",
        "Justification",
        "Composure",
        "Clarity",
    ]


def test_negotiation_validation(client, auth, docs, fire):
    assert create(client, auth, docs, format="negotiation").status_code == 400
    r = create(
        client, auth, docs, format="negotiation", negotiation=TERMS, duration_min=30
    )
    assert r.status_code == 400 and "5 to 20 minutes" in r.get_json()["error"]
    sid = create(client, auth, docs, format="negotiation", negotiation=TERMS)
    sid = sid.get_json()["session"]
    r = client.put(f"/api/sessions/{sid['id']}/plan", json=sid["plan"], headers=auth)
    assert r.status_code == 409


def test_negotiation_is_one_long_call_with_the_recruiter(app, client, auth, docs, fire):
    app.config["ICEBREAKER"] = True
    app.config["CANDIDATE_QUESTIONS"] = True
    sid = create(client, auth, docs, format="negotiation", negotiation=TERMS)
    sid = sid.get_json()["session"]["id"]
    segs = started(client, auth, sid)["transcript"][0]["segments"]
    # No small talk: straight into the call.
    assert segs[0]["text"].startswith("This is a 10-minute offer negotiation practice.")
    assert "I'll play Sam, the recruiter at Acme" in segs[0]["text"]
    assert segs[1]["who"] == "character" and "$80,000 base" in segs[1]["text"]

    fire.turns = [
        {"goal_reached": False, "action": "follow_up", "message": "What number?"}
    ] * 8
    for _ in range(8):  # more replies than a normal role-play allows
        data = answer(client, auth, sid, "I was hoping for more.").get_json()
        assert data["turn"]["action"] == "follow_up"
    prompt = fire.calls[-1]["prompt"]
    assert "only partway" in prompt  # the recruiter's private instructions
    assert "Your first reply never improves the offer" in prompt  # T-58

    fire.turns = [
        {"goal_reached": True, "action": "follow_up", "message": "Deal at $88,000!"}
    ]
    data = answer(client, auth, sid, "$88,000 and we have a deal.").get_json()
    # No "any questions for me?" after a negotiation.
    assert data["turn"]["action"] == "wrap_up"
    assert data["session"]["status"] == "completed"
    # The recruiter said goodbye; the app closes the practice, not an interview
    # ("you'll hear back by email", T-57).
    last = data["turn"]["segments"][-1]["text"]
    assert last.endswith(
        "That's the end of the negotiation practice, Ada. Your report shows how you did on anchoring, justifying your number and staying calm."
    )
    assert "email" not in data["turn"]["message"]


def test_negotiation_report_speaks_about_the_negotiation(app, client, auth, docs, fire):
    app.config["REPORTS_INLINE"] = True
    sid = create(client, auth, docs, format="negotiation", negotiation=TERMS)
    sid = sid.get_json()["session"]["id"]
    started(client, auth, sid)
    fire.turns = [{"goal_reached": True, "action": "wrap_up", "message": "Deal."}]
    answer(client, auth, sid, "I'd like $92,000 given my billing API work at Acme.")
    r = client.post(f"/api/sessions/{sid}/report", headers=auth).get_json()
    report = r["report"]
    assert report["mode"] == "negotiation"
    assert report["negotiation"] == TERMS
    summary = next(
        c for c in fire.calls if "summary for a mock-interview" in c["prompt"]
    )
    assert "an offer negotiation for Backend Engineer" in summary["prompt"]
    assert any(
        v in summary["prompt"] for v in negotiation.VERDICTS.values()
    ), "the verdict is worded for a negotiation"
