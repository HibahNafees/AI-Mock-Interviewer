"""Any-job support: format modules, interview type (focus) and role-play."""

import pytest

from app import modules
from app.services.interviewer import ROLEPLAY_EXIT
from app.services.planning import PlanSectionOut

from tests.fakes import PLAN
from tests.test_sessions import answer, started

SALES_ANALYSIS = {
    "role_title": "Account Executive",
    "field": "sales",
    "seniority": "mid",
    "competencies": [
        {"name": "Objection handling", "description": "Turns pushback into progress"},
        {"name": "Discovery", "description": "Asks good questions"},
    ],
    "formats": ["behavioral", "resume_deepdive", "roleplay"],
    "licensed_field": False,
}
SCENARIO = {
    "character": "Dana, an operations manager who thinks the price is too high",
    "setting": "A video call after your demo",
    "goal": "book a follow-up meeting with her finance lead",
}
OPENING = "Honestly, this looks expensive for what we need. Convince me."
SALES_PLAN = {
    "sections": [
        {
            "name": "Warm-up",
            "module": "behavioral",
            "minutes": 3,
            "questions": ["Tell me about a deal you closed."],
            "scenario": None,
        },
        {
            "name": "Sales call",
            "module": "roleplay",
            "minutes": 7,
            "questions": [OPENING],
            "scenario": SCENARIO,
        },
    ],
    "reserve": [],
}


def create(client, auth, docs, **extra):
    return client.post(
        "/api/sessions",
        json={**docs, "duration_min": 10, **extra},
        headers=auth,
    )


# ---- module registry --------------------------------------------------------


@pytest.mark.parametrize("name", list(modules.MODULES))
def test_every_module_has_plan_interview_and_score_guidance(name):
    for stage in ("plan", "interview", "score"):
        assert len(modules.guidance(name, stage)) > 40


def test_unknown_module_falls_back_to_behavioral():
    assert modules.guidance("juggling", "score") == modules.guidance(
        "behavioral", "score"
    )


# ---- interview type ---------------------------------------------------------


def test_analysis_offers_only_modules_that_fit_and_exist(client, auth, docs, fire):
    url = f"/api/documents/{docs['jd_id']}/analysis"
    res = client.post(url, headers=auth)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["analysis"]["role_title"] == "Backend Engineer"
    # "coding" fits the job but arrives in a later phase.
    assert [m["name"] for m in body["modules"]] == [
        "behavioral",
        "resume_deepdive",
        "technical",
    ]
    assert body["modules"][2]["label"] == "Technical Q&A"
    # Cached per document: setup can ask again for free.
    client.post(url, headers=auth)
    assert fire.kinds() == ["analysis"]


def test_analysis_needs_a_job_description(client, auth, docs):
    res = client.post(f"/api/documents/{docs['resume_id']}/analysis", headers=auth)
    assert res.status_code == 404


def test_focus_limits_the_plan_to_one_module(client, auth, docs, fire):
    res = create(client, auth, docs, focus="technical")
    assert res.status_code == 201, res.get_json()
    session = res.get_json()["session"]
    assert session["focus"] == "technical"
    # The model put a résumé section in anyway; it's coerced to the chosen module.
    assert {s["module"] for s in session["plan"]["sections"]} == {"technical"}
    plan_prompt, rubric_prompt = fire.calls[1]["prompt"], fire.calls[2]["prompt"]
    assert 'every section uses the "technical" module' in plan_prompt
    assert modules.guidance("technical", "plan") in plan_prompt
    assert modules.guidance("behavioral", "plan") not in plan_prompt
    assert "Technical Q&A questions only" in rubric_prompt


def test_mixed_loop_is_the_default(client, auth, docs, fire):
    session = create(client, auth, docs).get_json()["session"]
    assert session["focus"] == "mixed"
    assert "full interview loop" in fire.calls[1]["prompt"]
    assert modules.guidance("resume_deepdive", "plan") in fire.calls[1]["prompt"]


def test_focus_must_fit_the_job(client, auth, docs, fire):
    res = create(client, auth, docs, focus="roleplay")
    assert res.status_code == 400
    assert "doesn't fit" in res.get_json()["error"]


# ---- role-play --------------------------------------------------------------


def test_roleplay_section_needs_a_scenario():
    with pytest.raises(ValueError):
        PlanSectionOut(name="Call", module="roleplay", minutes=5, questions=["Hi"])
    other = PlanSectionOut(
        name="Q", module="technical", minutes=5, questions=["Q?"], scenario=SCENARIO
    )
    assert other.scenario is None


def test_plan_without_a_roleplay_scenario_is_retried(client, auth, docs, fire):
    fire.analysis = SALES_ANALYSIS
    broken = {
        **SALES_PLAN,
        "sections": [{**SALES_PLAN["sections"][1], "scenario": None}],
    }
    fire.plan = broken
    res = create(client, auth, docs)
    # The retry got the same broken plan, so the whole request fails cleanly.
    assert res.status_code == 502
    assert fire.kinds().count("plan") == 2


@pytest.fixture()
def sales(client, auth, docs, fire):
    fire.analysis = SALES_ANALYSIS
    fire.plan = SALES_PLAN
    res = create(client, auth, docs, persona="neutral")
    assert res.status_code == 201, res.get_json()
    return res.get_json()["session"]


def last_message(client, auth, sid):
    s = client.get(f"/api/sessions/{sid}", headers=auth).get_json()["session"]
    return s["transcript"][-1]["interviewer"]


def test_roleplay_is_announced_played_in_character_and_left(client, auth, sales, fire):
    sid = sales["id"]
    assert sales["plan"]["sections"][1]["scenario"] == SCENARIO
    started(client, auth, sid)

    # Moving into the role-play: the app announces it, then the planned opening.
    fire.turns = [{"action": "next_question", "message": "Okay. Let's do a call."}]
    reply = answer(client, auth, sid, "I closed a big renewal.").get_json()["turn"]
    msg = reply["message"]
    assert msg.startswith("Thanks. Let's switch to a role-play. I'll play Dana")
    assert "Your goal: book a follow-up meeting with her finance lead." in msg
    assert msg.endswith(OPENING)

    # In character: the role-play prompt is used and agreement isn't filtered out.
    in_character = "That sounds great, but who else uses this at our size?"
    fire.turns = [{"action": "follow_up", "message": in_character}] * 3
    for _ in range(3):  # more than the 2 follow-ups a normal question gets
        r = answer(client, auth, sid, "Let me ask what matters most to you.")
        assert r.get_json()["turn"]["action"] == "follow_up", r.get_json()
        assert r.get_json()["turn"]["message"] == in_character
    prompt = fire.calls[-1]["prompt"]
    assert "running a role-play" in prompt and SCENARIO["character"] in prompt
    assert modules.guidance("roleplay", "interview") in prompt
    assert "minutes left in this section" not in prompt  # no out-of-character nudges

    # Leaving: the app says so before the interviewer's closing.
    fire.turns = [{"action": "wrap_up", "message": "Thanks for your time today."}]
    r = answer(client, auth, sid, "Can we book a call with your finance lead?")
    assert (
        r.get_json()["turn"]["message"]
        == f"{ROLEPLAY_EXIT} Thanks for your time today."
    )


def test_interview_starting_with_a_roleplay_announces_it(client, auth, docs, fire):
    fire.analysis = SALES_ANALYSIS
    fire.plan = {**SALES_PLAN, "sections": [SALES_PLAN["sections"][1]]}
    sid = create(client, auth, docs, focus="roleplay").get_json()["session"]["id"]
    started(client, auth, sid)
    first = last_message(client, auth, sid)
    assert "Let's switch to a role-play." in first and first.endswith(OPENING)


def test_scorer_gets_module_guidance_and_the_scenario(client, auth, sales, fire):
    sid = sales["id"]
    started(client, auth, sid)
    fire.turns = [
        {"action": "next_question", "message": "Next."},
        {"action": "wrap_up", "message": "Thanks."},
    ]
    answer(client, auth, sid, "I closed a big renewal.")
    answer(client, auth, sid, "I hear you on price; what would it need to save you?")
    report = client.post(f"/api/sessions/{sid}/report", headers=auth).get_json()
    prompts = [c["prompt"] for c in fire.calls if "Score one question" in c["prompt"]]
    assert modules.guidance("behavioral", "score") in prompts[0]
    assert "Role-play scenario (JSON, or none): none" in prompts[0]
    assert modules.guidance("roleplay", "score") in prompts[1]
    assert SCENARIO["goal"] in prompts[1]
    roleplay_q = report["report"]["questions"][1]
    assert roleplay_q["module"] == "roleplay" and roleplay_q["scenario"] == SCENARIO


def test_plan_edits_keep_the_scenario(client, auth, sales):
    sid = sales["id"]
    plan = sales["plan"]
    plan["sections"][1]["questions"] = ["Why should I pay more than your rival?"]
    res = client.put(f"/api/sessions/{sid}/plan", json=plan, headers=auth)
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["session"]["plan"]["sections"][1]["scenario"] == SCENARIO
    # Dropping the scenario from a role-play section is rejected, not a crash.
    plan["sections"][1]["scenario"] = None
    res = client.put(f"/api/sessions/{sid}/plan", json=plan, headers=auth)
    assert res.status_code == 400
