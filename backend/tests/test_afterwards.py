"""Cheat sheet (no Fire call) and thank-you email (one call, kept)."""

from tests.test_reports import build, finished
from tests.test_stories import ETL, MENTOR, etl_story, interview


def test_cheat_sheet_uses_only_their_own_words(client, auth, planned, fire):
    fire.stories = [etl_story]
    sid = planned["id"]
    interview(client, auth, sid, ETL, MENTOR)
    calls = len(fire.calls)
    r = client.get(f"/api/sessions/{sid}/cheatsheet", headers=auth)
    assert r.status_code == 200, r.get_json()
    sheet = r.get_json()["sheet"]
    assert len(fire.calls) == calls  # no Fire call
    assert sheet["role_title"] == "Backend Engineer"
    assert sheet["stories"][0]["title"] == "Cut API latency with a nightly ETL"
    assert any("1.8 seconds" in n for n in sheet["key_numbers"])
    assert sheet["takeaways"]
    assert sheet["likely_questions"]  # questions they never got to


def test_thank_you_email_is_drafted_once(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    r = client.post(f"/api/sessions/{sid}/thank-you", headers=auth)
    assert r.status_code == 200, r.get_json()
    email = r.get_json()["email"]
    assert (
        email["subject"] == "Thank you for today"
        and "[Interviewer's name]" in email["body"]
    )
    prompt = fire.calls[-1]["prompt"]
    assert "Candidate's first name: Ada" in prompt and "Company: unknown" in prompt
    assert "Never invent facts" in prompt
    calls = len(fire.calls)
    client.post(f"/api/sessions/{sid}/thank-you", headers=auth)
    assert len(fire.calls) == calls


def test_both_need_a_ready_report(client, auth, planned):
    sid = planned["id"]
    assert (
        client.get(f"/api/sessions/{sid}/cheatsheet", headers=auth).status_code == 409
    )
    assert (
        client.post(f"/api/sessions/{sid}/thank-you", headers=auth).status_code == 409
    )
