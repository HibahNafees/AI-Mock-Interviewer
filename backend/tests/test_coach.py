"""Questions-for-them coach: suggestions per job, ratings for the ones asked."""

from tests.test_candidate_questions import qa, reach_the_end  # noqa: F401
from tests.test_reports import build
from tests.test_sessions import answer


def test_suggestions_for_a_job_are_cached(client, auth, docs, fire):
    url = f"/api/documents/{docs['jd_id']}/questions-to-ask"
    r = client.post(url, headers=auth)
    assert r.status_code == 200, r.get_json()
    c = r.get_json()["coach"]
    assert (
        c["questions"][0]["question"]
        == "What would success look like in the first 90 days?"
    )
    assert c["avoid"] == ["Asking about salary in the first round."]
    calls = len(fire.calls)
    client.post(url, headers=auth)
    assert len(fire.calls) == calls


def test_questions_they_asked_are_rated_in_the_report(
    qa, client, auth, planned, fire
):  # noqa: F811
    sid = planned["id"]
    reach_the_end(client, auth, fire, sid)
    fire.candidate_replies = [
        {"has_question": True, "answer": "Mostly API work."},
        {"has_question": False, "answer": "Great."},
    ]
    answer(client, auth, sid, "What does a typical week look like?")
    answer(client, auth, sid, "No, that's all.")
    report = build(client, auth, sid).get_json()["report"]
    t = report["their_questions"]
    # Only questions really asked are kept (the fake also "rates" one never asked).
    assert [q["asked"] for q in t["questions"]] == [
        "What does a typical week look like?"
    ]
    assert t["questions"][0]["better"] == "What would my first project be?"


def test_no_questions_no_rating_call(qa, client, auth, planned, fire):  # noqa: F811
    sid = planned["id"]
    reach_the_end(client, auth, fire, sid)
    answer(client, auth, sid, "No, I think you've covered everything.")
    report = build(client, auth, sid).get_json()["report"]
    assert report["their_questions"] is None
    assert not any("Rate the candidate's questions" in c["prompt"] for c in fire.calls)
