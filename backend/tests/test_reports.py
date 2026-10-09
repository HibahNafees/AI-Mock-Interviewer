import io

import pytest

from app.extensions import db
from app.models import Answer, Evaluation, Report, UsageLimit
from app.services.analytics import Clip, delivery, filler_counts, session_summary
from app.services.fire import FireError
from app.services.limits import today
from app.services.scoring import (
    FALLBACK_REWRITE,
    CriterionScore,
    _detach,
    _keep,
    Sentence,
    grounding_problems,
    resume_fallback,
    split_sentences,
    verdict_for,
    weighted_score,
)

from tests.conftest import RESUME
from tests.fakes import SCORE
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


def test_untested_criteria_are_left_out_of_the_score():
    rubric = {
        "criteria": [
            {"name": "SQL", "weight": 0.5},
            {"name": "Mentoring", "weight": 0.3},
            {"name": "Clarity", "weight": 0.2},
        ]
    }
    scores = [
        CriterionScore(name="SQL", score=None),
        CriterionScore(name="Mentoring", score=4),
        CriterionScore(name="Clarity", score=2),
    ]
    score, rows = weighted_score(scores, rubric)
    assert score == pytest.approx(3.2)  # (4×0.3 + 2×0.2) / 0.5, SQL ignored
    assert [r["name"] for r in rows] == ["Mentoring", "Clarity"]


LIVE_RESUME = (
    "Acme Payments: Built the refunds API in Python/Flask serving 2M requests/day; "
    "moved reporting queries from MySQL replicas to a nightly ETL, cutting p95 "
    "latency from 1.8s to 300ms; mentored two junior engineers."
)


def test_hedges_are_cut_from_the_stronger_version():
    # Live (T-24): "I'm not sure about that one; I'd look at…" was copied verbatim.
    out = split_sentences(
        [
            Sentence(
                text="I'm not sure about that one; I'd check the pool size first."
            ),
            Sentence(text="I don't know."),
            Sentence(text="I made sure the pool was sized right."),
        ]
    )
    assert [s.text for s in out] == [
        "I'd check the pool size first.",
        "I made sure the pool was sized right.",
    ]


def test_hypothetical_answers_are_not_turned_into_experience():
    answer = "I'd use a token bucket per API key in Redis, with a Lua script."
    claimed = Sentence(text="At Acme I built a token bucket per API key in Redis.")
    kept_hypothetical = Sentence(text="I'd use a token bucket per API key in Redis.")
    assert grounding_problems([claimed, kept_hypothetical], [LIVE_RESUME, answer]) == [
        "it presents what the candidate said they would do as something they did",
        "",
    ]


@pytest.mark.parametrize(
    "text,source,problem",
    [
        # Grounded rewording of the résumé.
        (
            "At Acme Payments I built the refunds API in Python and Flask.",
            "Built the refunds API in Python/Flask",
            "",
        ),
        ("That cut latency by [add the % improvement].", None, ""),
        # Invented in the live check (T-15).
        (
            "I also collaborated closely with product teams to gather requirements.",
            None,
            "it adds details the candidate never gave",
        ),
        # Faithful sentences pass without a cited source (the model often omits it).
        ("I set up the alerts and mentored two junior engineers.", None, ""),
        (
            "I designed the endpoints to be stateless, allowing easy horizontal scaling.",
            "Built the refunds API",
            "it adds details the candidate never gave",
        ),
        (
            "I organized regular one-on-one sessions with [names] every week.",
            None,
            "it adds details the candidate never gave",
        ),
        # Unit conversions and framing aren't new facts.
        (
            "To address this, we moved reporting queries to a nightly ETL, which cut "
            "p95 latency from 1.8 seconds to 300 milliseconds.",
            "moved reporting queries from MySQL replicas to a nightly ETL",
            "",
        ),
        # A grounded start can't carry an invented clause.
        (
            "I built the refunds API in Python and Flask, ensuring it was optimized "
            "for performance.",
            "Built the refunds API in Python/Flask",
            "it adds details the candidate never gave",
        ),
        (
            "It served 5 million requests a day.",
            "serving 2M requests/day",
            "it uses numbers the candidate never gave (5)",
        ),
    ],
)
def test_grounding_flags_invented_sentences(text, source, problem):
    sentence = Sentence(text=text, source=source)
    assert grounding_problems([sentence], [LIVE_RESUME, "I set up the alerts."]) == [
        problem
    ]


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
    # The untested criterion isn't shown or counted.
    ev0 = report["questions"][0]["evaluation"]
    assert [c["name"] for c in ev0["criteria"]] == [
        "API design",
        "Structure",
        "Clarity",
        "Relevance",
    ]
    assert report["verdict_reason"].startswith("Solid ownership")

    first = report["questions"][0]
    assert first["text"] == "Walk me through your Acme project."
    assert [e["is_follow_up"] for e in first["exchange"]] == [False, True]
    ev = first["evaluation"]
    assert ev["stronger_version"] == (
        "At Acme I built the billing API. That led to [add the result you achieved]."
    )
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
    # Typed answers are marked as not spoken (spoken ones may have mishearings).
    assert '"spoken": false' in score_prompt and "transcription error" in score_prompt
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


def test_paragraph_items_are_checked_sentence_by_sentence():
    item = Sentence(
        text="I built the refunds API. I also added caching strategies everywhere.",
        source="Built the refunds API",
    )
    parts = split_sentences([item])
    assert [p.text for p in parts] == [
        "I built the refunds API.",
        "I also added caching strategies everywhere.",
    ]
    assert grounding_problems(parts, [LIVE_RESUME]) == [
        "",
        "it adds details the candidate never gave",
    ]


FULL_RESUME = (
    "Sam Rivera — Backend Engineer\n"
    + LIVE_RESUME
    + "\nBright Labs (2019–2021): Wrote internal REST services in Django; "
    "added Redis caching; on-call rotation.\nSkills: Python, Flask, MySQL."
)


@pytest.mark.parametrize(
    "question,expected",
    [
        (
            "Can you describe a time when you had to mentor junior engineers?",
            "At Acme Payments, I mentored two junior engineers. [Describe one",
        ),
        (
            "Walk me through a Django service you wrote.",
            "At Bright Labs, I wrote internal REST services in Django. [Describe",
        ),
        (
            "Tell me about an on-call incident.",
            '[Build this from your résumé: "on-call rotation".] [Describe',
        ),
        ("How do you handle conflict with a product manager?", FALLBACK_REWRITE),
    ],
)
def test_fallback_starts_from_the_matching_resume_line(question, expected):
    assert resume_fallback(question, FULL_RESUME).startswith(expected)


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "This change cut latency to 300ms.",
            "[What you changed] cut latency to 300ms.",
        ),
        (
            "These keys ensured no double refunds.",
            "The keys ensured no double refunds.",
        ),
        ("For instance, I moved the queries.", "I moved the queries."),
        ("To address this, we added alerts.", "We added alerts."),
        ("They designed the tables.", "They designed the tables."),
        ("This was at Acme.", "This was at Acme."),
    ],
)
def test_detach_rewrites_openers_that_point_at_a_dropped_sentence(text, expected):
    assert _detach(text) == expected


def test_kept_sentences_are_detached_only_after_a_gap():
    sentences = [
        Sentence(text="I built the API."),
        Sentence(text="This change cut latency."),
        Sentence(text="It served 9 million users."),
        Sentence(text="This change cut latency."),
    ]
    kept = _keep(sentences, ["", "", "it uses numbers", ""])
    assert [s.text for s in kept] == [
        "I built the API.",
        "This change cut latency.",
        "[What you changed] cut latency.",
    ]


def invented(*sentences: dict) -> dict:
    return {**SCORE, "stronger_version": list(sentences)}


GOOD = {
    "text": "At Acme I built the billing API.",
    "source": "Built the Acme billing API",
}
MADE_UP = {"text": "It handled 9 million requests a day.", "source": None}


def test_invented_rewrite_is_repaired_once(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = [invented(GOOD, MADE_UP), invented(GOOD)]
    before = len(fire.calls)
    report = build(client, auth, sid).get_json()["report"]
    assert fire.kinds()[before:] == ["score", "repair", "score", "summary"]
    repair = fire.calls[before + 1]["prompt"]
    assert "Sentence 2: it uses numbers the candidate never gave (9)." in repair
    assert "Sentence 1:" not in repair
    first = report["questions"][0]["evaluation"]["stronger_version"]
    assert (
        first
        == "I built the Acme billing API. The result was [add the result you achieved]."
    )
    # "What changed" described the rejected rewrite, so it isn't shown.
    assert report["questions"][0]["evaluation"]["changes"] == []
    assert report["questions"][1]["evaluation"]["changes"] == SCORE["changes"]
    second = report["questions"][1]["evaluation"]["stronger_version"]
    assert second == "At Acme I built the billing API."


def test_still_invented_sentences_are_dropped(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = [invented(GOOD, MADE_UP), invented(MADE_UP)]
    fire.repairs = [invented(MADE_UP, GOOD), invented(MADE_UP)]
    report = build(client, auth, sid).get_json()["report"]
    assert fire.kinds().count("repair") == 2
    evs = [q["evaluation"]["stronger_version"] for q in report["questions"]]
    # Never shown: the invented sentence. Nothing grounded left → a placeholder.
    assert evs == ["At Acme I built the billing API.", FALLBACK_REWRITE]
    # Sentences were dropped, so no "what changed" list describes unseen text.
    assert [q["evaluation"]["changes"] for q in report["questions"]] == [[], []]


def test_placeholder_only_rewrite_falls_back_to_the_resume(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    bare = {"text": "[add the result you achieved] [name the tool you used]"}
    fire.scores = [invented(bare), invented(GOOD)]
    report = build(client, auth, sid).get_json()["report"]
    first = report["questions"][0]["evaluation"]["stronger_version"]
    assert first.startswith("I built the Acme billing API in Python and MySQL.")


def test_all_criteria_untested_is_retried(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    none = [{**c, "score": None} for c in SCORE["criteria"]]
    fire.scores = [{**SCORE, "criteria": none}]
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
    "stronger_version": [GOOD],
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


def test_spoken_retry_is_flagged_for_transcription_slips(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    qid = report["report"]["questions"][0]["question_id"]
    assert retry(client, auth, sid, qid).status_code == 201
    assert '"spoken": true' in fire.calls[-1]["prompt"]


# Live (T-29): the rewrite added an impact the candidate never claimed.
EMOTION_ANSWER = (
    "I worked with Python and OpenCV to make the learning experience more engaging. "
    "We reached about 85 to 90% accuracy in testing."
)


@pytest.mark.parametrize(
    "text, problem",
    [
        (
            "I reached about 85 to 90% accuracy, which significantly improved user "
            "engagement.",
            "it claims an impact the candidate never stated (engagement, significantly)",
        ),
        (
            "That increased retention for our learners.",
            "it claims an impact the candidate never stated (retention)",
        ),
        ("We reached about 85 to 90% accuracy in testing.", ""),
        ("That made learning more engaging: [add the result you measured].", ""),
    ],
)
def test_grounding_flags_invented_impact(text, problem):
    assert grounding_problems([Sentence(text=text)], [EMOTION_ANSWER]) == [problem]


def test_try_again_is_scored_on_the_first_attempts_criteria(
    client, auth, planned, fire
):
    # Live (T-29): the first answer was scored on 3 criteria and the retry on 6, so
    # the suggested stronger version scored lower than the original.
    sid = planned["id"]
    fire.scores = [
        {
            **SCORE_ALL_FIVE,
            "criteria": [
                {"name": "API design", "score": None},
                {"name": "Structure", "score": 3},
                {"name": "Clarity", "score": 4},
                {"name": "Relevance", "score": 4},
            ],
        }
    ]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    qid = report["report"]["questions"][0]["question_id"]

    # The scorer first drops a criterion, is told to score it, then complies.
    partial = {
        **SCORE_ALL_FIVE,
        "criteria": [
            {"name": "Structure", "score": 5},
            {"name": "Clarity", "score": 5},
        ],
    }
    fire.scores = [partial, {**SCORE_ALL_FIVE, "criteria": SCORE_ALL_FIVE["criteria"]}]
    body = retry(client, auth, sid, qid).get_json()

    prompt = fire.calls[-2]["prompt"]
    assert "This answer is a retry" in prompt
    assert '"name": "API design"' not in prompt  # not scored the first time
    assert "missing: Relevance" in fire.calls[-1]["messages"][-1]["content"]
    criteria = body["attempt"]["evaluation"]["criteria"]
    assert [c["name"] for c in criteria] == ["Structure", "Clarity", "Relevance"]
    assert body["attempt"]["evaluation"]["score"] == 5


def test_scoring_runs_at_temperature_zero(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    scoring = [c for c in fire.calls if c["prompt"].startswith("Score one question")]
    assert scoring and {c["temperature"] for c in scoring} == {0}
