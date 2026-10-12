"""Ice-breaker opener and the natural sign-off."""

import pytest

from app.services.fire import FireError
from app.services.interviewer import CLOSINGS, ICEBREAKERS, TOUGH_CLOSING

from tests.fakes import PLAN
from tests.test_modules import SALES_ANALYSIS, SALES_PLAN, create
from tests.test_sessions import answer, started


@pytest.fixture()
def icebreaker(app):
    app.config["ICEBREAKER"] = True


def test_interview_opens_with_small_talk_then_the_plan(
    icebreaker, client, auth, planned, fire
):
    sid = planned["id"]
    session = started(client, auth, sid)
    first = session["transcript"][0]["interviewer"]
    assert first.startswith("Hi Ada, thanks for joining!")
    assert any(first.endswith(q) for q in ICEBREAKERS)
    assert session["timer"]["section"] is None  # not part of any section

    r = answer(client, auth, sid, "Good, thanks! A bit nervous.").get_json()
    prompt = fire.calls[-1]["prompt"]
    assert "moment of small talk" in prompt and "A bit nervous." in prompt
    planned_q = PLAN["sections"][0]["questions"][0]
    assert r["turn"]["message"] == (
        f"Doing well, thanks for asking! Let's get started. {planned_q}"
    )
    assert r["session"]["timer"]["section"] == PLAN["sections"][0]["name"]


def test_small_talk_is_never_scored(icebreaker, client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    answer(client, auth, sid, "Doing great, thank you for having me today.")
    answer(client, auth, sid, "I built the billing API at Acme and owned the schema.")
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    report = client.post(f"/api/sessions/{sid}/report", headers=auth).get_json()
    texts = [q["text"] for q in report["report"]["questions"]]
    assert texts == [PLAN["sections"][0]["questions"][0]]


def test_small_talk_reply_falls_back_when_fire_fails(
    icebreaker, client, auth, planned, fire
):
    sid = planned["id"]
    started(client, auth, sid)
    fire.small_talk_error = FireError("down")
    r = answer(client, auth, sid, "Fine, thanks.")
    assert r.status_code == 200
    assert r.get_json()["turn"]["message"].startswith("Thanks for sharing. ")


def test_roleplay_is_announced_after_the_small_talk(
    icebreaker, client, auth, docs, fire
):
    fire.analysis = SALES_ANALYSIS
    fire.plan = {**SALES_PLAN, "sections": [SALES_PLAN["sections"][1]]}
    sid = create(client, auth, docs).get_json()["session"]["id"]
    started(client, auth, sid)
    segments = answer(client, auth, sid, "Great, thanks!").get_json()["turn"][
        "segments"
    ]
    assert [s["who"] for s in segments] == ["interviewer", "character"]
    assert "Let's switch to a role-play." in segments[0]["text"]


def test_model_wrap_up_becomes_a_natural_sign_off(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    # Skip ahead so wrap_up is allowed: answer every planned question first.
    fire.turns = [{"action": "next_question", "message": "Next."}] * 2 + [
        {"action": "wrap_up", "message": "Thanks."}
    ]
    for _ in range(3):
        turn = answer(
            client, auth, sid, "An answer with enough words in it."
        ).get_json()
    message = turn["turn"]["message"]
    assert turn["turn"]["action"] == "wrap_up"
    assert any(c.format(name="Ada") == message for c in CLOSINGS)
    assert "email" in message


def test_tough_interviewer_signs_off_briefly(client, auth, docs, fire):
    sid = create(client, auth, docs, persona="tough").get_json()["session"]["id"]
    started(client, auth, sid)
    fire.turns = [{"action": "next_question", "message": "Next."}] * 2 + [
        {"action": "wrap_up", "message": "Thanks."}
    ]
    for _ in range(3):
        turn = answer(
            client, auth, sid, "An answer with enough words in it."
        ).get_json()
    assert turn["turn"]["message"] == TOUGH_CLOSING.format(name="Ada")


def test_small_talk_reply_drops_questions_and_its_own_transition(
    icebreaker, client, auth, planned, fire
):
    """T-98: the app adds "Let's get started." itself."""
    sid = planned["id"]
    started(client, auth, sid)
    fire.small_talk_reply = (
        "Glad to hear it. Coffee helps, doesn't it? Let's get started."
    )
    r = answer(client, auth, sid, "Good, just had coffee.").get_json()
    planned_q = PLAN["sections"][0]["questions"][0]
    assert r["turn"]["message"] == f"Glad to hear it. Let's get started. {planned_q}"


def test_small_talk_reply_that_is_only_a_question_falls_back(
    icebreaker, client, auth, planned, fire
):
    sid = planned["id"]
    started(client, auth, sid)
    fire.small_talk_reply = "Ready to begin?"
    r = answer(client, auth, sid, "Sure.").get_json()
    assert r["turn"]["message"].startswith("Thanks for sharing. Let's get started. ")
