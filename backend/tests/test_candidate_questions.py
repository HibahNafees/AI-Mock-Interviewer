"""'Do you have any questions for me?' at the end of the interview."""

import pytest

from app.services.fire import FireError
from app.services.interviewer import ANYTHING_ELSE, CLOSINGS, INVITE, INVITE_LATE

from tests.test_sessions import answer, started


@pytest.fixture()
def qa(app):
    app.config["CANDIDATE_QUESTIONS"] = True


def reach_the_end(client, auth, fire, sid):
    """Answer every planned question; the model then wraps up."""
    started(client, auth, sid)
    fire.turns = [{"action": "next_question", "message": "Next."}] * 2 + [
        {"action": "wrap_up", "message": "Thanks."}
    ]
    for _ in range(3):
        turn = answer(client, auth, sid, "An answer with enough words in it.")
    return turn.get_json()


def is_closing(message):
    return any(c.format(name="Ada") in message for c in CLOSINGS)


def test_interviewer_invites_questions_instead_of_signing_off(
    qa, client, auth, planned, fire
):
    body = reach_the_end(client, auth, fire, planned["id"])
    assert body["turn"]["action"] == "your_questions"
    assert body["turn"]["message"] == INVITE
    assert body["session"]["status"] == "active"
    assert body["session"]["transcript"][-1]["interviewer"] == INVITE


def test_no_questions_gets_a_friendly_sign_off(qa, client, auth, planned, fire):
    sid = planned["id"]
    reach_the_end(client, auth, fire, sid)
    body = answer(
        client, auth, sid, "No, I think you've covered everything."
    ).get_json()
    assert body["turn"]["action"] == "wrap_up"
    assert body["turn"]["message"].startswith("No problem at all. ")
    assert is_closing(body["turn"]["message"])
    assert body["session"]["status"] == "completed"


def test_a_question_is_answered_from_the_job_description(
    qa, client, auth, planned, fire
):
    sid = planned["id"]
    reach_the_end(client, auth, fire, sid)
    fire.candidate_replies = [
        {"has_question": True, "answer": "Day to day you'd own our payment APIs."},
        {"has_question": False, "answer": "Great."},
    ]
    body = answer(client, auth, sid, "What does a typical day look like?").get_json()
    prompt = fire.calls[-1]["prompt"]
    assert "What does a typical day look like?" in prompt
    assert "Job description:" in prompt and "Backend Engineer" in prompt
    assert body["turn"]["action"] == "your_questions"
    assert body["turn"]["message"] == (
        f"Day to day you'd own our payment APIs. {ANYTHING_ELSE}"
    )

    body = answer(client, auth, sid, "No, that's all. Thank you!").get_json()
    assert body["session"]["status"] == "completed"
    # The earlier question and answer are passed along as context.
    assert "What does a typical day look like?" in fire.calls[-1]["prompt"]


def test_at_most_three_questions(qa, client, auth, planned, fire):
    sid = planned["id"]
    reach_the_end(client, auth, fire, sid)
    fire.candidate_replies = [{"has_question": True, "answer": "Good question."}] * 3
    actions = [
        answer(client, auth, sid, f"Question {n}?").get_json()["turn"]["action"]
        for n in range(3)
    ]
    assert actions == ["your_questions", "your_questions", "wrap_up"]


def test_candidate_questions_are_never_scored(qa, client, auth, planned, fire):
    sid = planned["id"]
    reach_the_end(client, auth, fire, sid)
    answer(client, auth, sid, "No questions, thanks so much for your time.")
    report = client.post(f"/api/sessions/{sid}/report", headers=auth).get_json()
    texts = [q["text"] for q in report["report"]["questions"]]
    assert INVITE not in texts and len(texts) == 3


def test_out_of_time_still_invites_briefly(qa, app, client, auth, planned, fire):
    from datetime import timedelta

    from app.extensions import db
    from app.models import Session

    sid = planned["id"]
    started(client, auth, sid)
    session = db.session.get(Session, sid)
    session.started_at -= timedelta(minutes=10)
    db.session.commit()
    body = answer(client, auth, sid, "An answer with enough words in it.").get_json()
    assert body["turn"]["message"].endswith(INVITE_LATE)


def test_fire_failure_signs_off_politely(qa, client, auth, planned, fire):
    sid = planned["id"]
    reach_the_end(client, auth, fire, sid)
    fire.candidate_replies = [FireError("down")]
    body = answer(client, auth, sid, "What are the next steps?").get_json()
    assert body["turn"]["action"] == "wrap_up" and is_closing(body["turn"]["message"])
