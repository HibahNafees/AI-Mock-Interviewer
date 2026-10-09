import io

import pytest

from app.extensions import db
from app.models import Answer, Evaluation, Report, UsageLimit
from app.services.analytics import Clip, delivery, filler_counts, session_summary
from app.services.fire import FireError
from app.services.limits import today
from app.services.scoring import CriterionScore, verdict_for, weighted_score

from tests.conftest import RESUME
from tests.test_transcription import CLIP
from tests.test_sessions import answer, started


def finished(client, auth, fire, session_id):
    """Run a short interview: main question + follow-up, then a second question."""
    started(client, auth, session_id)
    fire.turns = [
        {"action": "follow_up", "message": "What was your specific part?"},
        {"action": "next_question", "message": "How would you design a rate limiter?"},
    ]
    answer(client, auth, session_id, "Um, I built the billing API at Acme.", 60_000)
    answer(client, auth, session_id, "I owned the schema.", 20_000)
    answer(client, auth, session_id, "My answer about token buckets.", 90_000)
    res = client.post(f"/api/sessions/{session_id}/end", headers=auth)
    assert res.get_json()["session"]["status"] == "completed"


def build(client, auth, session_id):
    return client.post(f"/api/sessions/{session_id}/report", headers=auth)


# ---- analytics (no Fire) ---------------------------------------------------


def test_filler_counts():
    text = "Um, so uh, I think, umm, you know, we shipped. You know what I mean?"
    assert filler_counts(text) == {"um": 2, "uh": 1, "you know": 1}


def test_delivery_pace_fillers_and_tips():
    words = " ".join(["word"] * 200) + " um uh um um um um um um"
    d = delivery([Clip(words, 60_000, "voice")], budget_sec=30)
    assert d["wpm"] == 208 and d["filler_total"] == 8
    assert d["fillers_per_min"] == 8.0
    joined = " ".join(d["tips"])
    assert "slow down" in joined and "filler" in joined
    # Budgets under a minute don't trigger the "too long" tip.
    assert "budget" not in joined


def test_typed_answers_have_no_pace_or_fillers():
    d = delivery([Clip("Um, I typed this.", 60_000, "text")], budget_sec=240)
    assert d["wpm"] is None and d["fillers"] == {} and not d["spoken"]
    assert any("short" in t for t in d["tips"])  # 60 s of a 4-minute budget


def test_long_answer_tip_and_summary():
    long = delivery([Clip("x " * 300, 400_000, "voice")], budget_sec=180)
    assert any("against a 3.0 min budget" in t for t in long["tips"])
    s = session_summary([long, delivery([Clip("y", 5_000, "voice")], 120)])
    assert s["over_budget"] == 1 and s["questions"] == 2 and s["avg_wpm"] == 45


def test_weighted_score_uses_rubric_weights():
    rubric = {
        "criteria": [
            {"name": "API design", "weight": 0.6},
            {"name": "Clarity", "weight": 0.4},
        ]
    }
    scores = [
        CriterionScore(name="api design", score=5),
        CriterionScore(name="Clarity", score=2),
        CriterionScore(name="Made up", score=1),
    ]
    score, rows = weighted_score(scores, rubric)
    assert score == pytest.approx(3.8)
    assert [r["name"] for r in rows] == ["API design", "Clarity"]
    # Every name changed: fall back to a plain average.
    assert weighted_score([CriterionScore(name="X", score=4)], rubric)[0] == 4


def test_verdicts():
    assert [verdict_for(s) for s in (4.2, 3.0, 2.9)] == ["hire", "lean hire", "no hire"]


# ---- report generation ---------------------------------------------------


def test_report_scores_each_question_then_summarizes(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    before = len(fire.calls)
    res = build(client, auth, sid)
    assert res.status_code == 202, res.get_json()
    report = res.get_json()["report"]
    assert fire.kinds()[before:] == ["score", "score", "summary"]

    assert report["status"] == "ready"
    assert report["progress"] == {"scored": 2, "total": 2}
    # Weights 0.4/0.2/0.2/0.2 over scores 4/3/4/2 → 3.4 (computed here, not by the AI).
    assert report["overall_score"] == pytest.approx(3.4)
    assert report["verdict"] == "lean hire"
    assert report["takeaways"] == SUMMARY_TAKEAWAYS
    assert report["verdict_reason"].startswith("Solid ownership")

    first = report["questions"][0]
    assert first["text"] == "Walk me through your Acme project."
    assert [e["is_follow_up"] for e in first["exchange"]] == [False, True]
    ev = first["evaluation"]
    assert ev["stronger_version"].endswith("[add the result you achieved].")
    # Only quotes the candidate actually said survive (for highlighting).
    assert [w["quote"] for w in ev["weak_moments"]] == []
    second = report["questions"][1]["evaluation"]
    assert [w["quote"] for w in second["weak_moments"]] == ["My answer"]
    # Delivery covers the main answer plus its follow-up.
    assert first["delivery"]["duration_sec"] == 80
    assert first["delivery"]["words"] == 12
    assert report["analytics"]["questions"] == 2

    # The scorer sees the résumé, the rubric and the follow-up exchange.
    score_prompt = fire.calls[before]["prompt"]
    assert RESUME in score_prompt and "I owned the schema." in score_prompt
    assert '"name": "API design"' in score_prompt

    # Asking again doesn't pay twice.
    again = build(client, auth, sid)
    assert again.status_code == 202 and len(fire.calls) == before + 3
    got = client.get(f"/api/sessions/{sid}/report", headers=auth)
    assert got.get_json()["report"]["overall_score"] == pytest.approx(3.4)


SUMMARY_TAKEAWAYS = ["Quantify results.", "Lead with the point.", "Keep answers tight."]


def test_failed_question_is_resumed_without_rescoring(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = [FireError("The AI service is busy", 429)]
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "failed"
    assert report["progress"] == {"scored": 1, "total": 2}
    assert report["questions"][0]["evaluation"] is None
    assert report["questions"][0]["delivery"]["words"] == 12  # analytics still shown

    before = len(fire.calls)
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    assert fire.kinds()[before:] == ["score", "summary"]
    assert Evaluation.query.count() == 2


def test_invalid_scorer_json_is_retried_once(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = ['{"criteria": []}']
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    assert fire.kinds().count("score") == 3


def test_report_needs_a_finished_interview(client, auth, planned, fire):
    sid = planned["id"]
    assert client.get(f"/api/sessions/{sid}/report", headers=auth).status_code == 404
    assert build(client, auth, sid).status_code == 409
    started(client, auth, sid)
    assert build(client, auth, sid).status_code == 409


def test_report_respects_monthly_budget(app, client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    row = db.session.get(UsageLimit, (1, today()))
    row.fire_spend_usd = 5
    db.session.commit()
    res = build(client, auth, sid)
    assert res.status_code == 429 and "budget" in res.get_json()["error"]
    assert Report.query.count() == 0


def test_reports_are_private(client, auth, planned, fire, signup):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    token = signup(email="eve@example.com").get_json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/sessions/{sid}/report", headers=other).status_code == 404
    assert build(client, other, sid).status_code == 404


# ---- Try again -------------------------------------------------------------


def retry(client, auth, sid, qid, text="A tighter answer with a result.", **extra):
    return client.post(
        f"/api/sessions/{sid}/questions/{qid}/retry",
        json={"text": text, "duration_ms": 45_000, "input_mode": "voice", **extra},
        headers=auth,
    )


def test_try_again_shows_before_and_after(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    qid = report["report"]["questions"][0]["question_id"]

    better = {**SCORE_ALL_FIVE}
    fire.scores = [better]
    res = retry(client, auth, sid, qid)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["before_score"] == pytest.approx(3.4)
    assert body["attempt"]["attempt_no"] == 2
    assert body["attempt"]["evaluation"]["score"] == 5

    # The retry is scored alone, against the planned wording of the question.
    prompt = fire.calls[-1]["prompt"]
    assert "Walk me through your Acme project." in prompt
    assert "I owned the schema." not in prompt

    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    q = report["report"]["questions"][0]
    assert [a["attempt_no"] for a in q["attempts"]] == [2]
    assert q["evaluation"]["score"] == pytest.approx(3.4)  # original kept
    # The interview transcript still shows only the original answers.
    s = client.get(f"/api/sessions/{sid}", headers=auth).get_json()["session"]
    assert "A tighter answer with a result." not in [
        t["answer"] for t in s["transcript"]
    ]

    assert retry(client, auth, sid, qid).get_json()["attempt"]["attempt_no"] == 3


SCORE_ALL_FIVE = {
    "criteria": [
        {"name": n, "score": 5}
        for n in ("API design", "Structure", "Clarity", "Relevance")
    ],
    "summary": "Clear and complete.",
    "stronger_version": "Already strong.",
}


def test_try_again_validation(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    fire.turns = [{"action": "follow_up", "message": "What was your part?"}]
    answer(client, auth, sid)
    s = client.get(f"/api/sessions/{sid}", headers=auth).get_json()["session"]
    root, follow = s["transcript"][0]["question_id"], s["transcript"][1]["question_id"]
    assert retry(client, auth, sid, root).status_code == 409  # still running
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    assert retry(client, auth, sid, follow).status_code == 404  # follow-ups: no
    assert retry(client, auth, sid, 999).status_code == 404
    assert retry(client, auth, sid, root, text="  ").status_code == 400


def test_failed_retry_is_not_kept(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    qid = Answer.query.first().question_id
    fire.scores = [FireError("The AI service is busy", 429)]
    res = retry(client, auth, sid, qid)
    assert res.status_code == 429
    assert Answer.query.filter(Answer.attempt_no > 1).count() == 0
    # The failed call's spend is still recorded.
    assert db.session.get(UsageLimit, (1, today())).llm_calls > 0


def test_try_again_daily_cap(app, client, auth, planned, fire):
    app.config["DAILY_RETRIES"] = 1
    sid = planned["id"]
    finished(client, auth, fire, sid)
    qid = Answer.query.first().question_id
    assert retry(client, auth, sid, qid).status_code == 201
    res = retry(client, auth, sid, qid)
    assert res.status_code == 429 and "retries" in res.get_json()["error"]
    clip = client.post(
        f"/api/sessions/{sid}/transcribe",
        data={"audio": (io.BytesIO(CLIP), "a.webm", "audio/webm")},
        headers=auth,
    )
    assert clip.status_code == 429


def test_transcribe_works_after_the_interview_for_retries(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.transcripts = ["A spoken retry."]
    res = client.post(
        f"/api/sessions/{sid}/transcribe",
        data={"audio": (io.BytesIO(CLIP), "a.webm", "audio/webm")},
        headers=auth,
    )
    assert res.status_code == 200 and res.get_json()["text"] == "A spoken retry."
