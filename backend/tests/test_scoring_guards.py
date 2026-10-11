"""Scorer guards from the T-74 eval: weights, untested criteria, non-results."""

import pytest

from app.services.planning import share_weights
from app.services.scoring import (
    CriterionScore,
    ScoreOut,
    drop_untested,
    states_outcome,
    verify_coverage,
    weighted_score,
)

RUBRIC = {
    "criteria": [
        {"name": "Objection handling", "kind": "role", "weight": 0.5},
        {"name": "Resilience", "kind": "role", "weight": 0.3},
        {"name": "Structure", "kind": "universal", "weight": 0.05},
        {"name": "Clarity", "kind": "universal", "weight": 0.05},
        {"name": "Relevance", "kind": "universal", "weight": 0.05},
    ]
}


def test_communication_is_thirty_percent_whatever_the_model_weighted():
    w = share_weights(RUBRIC["criteria"])
    assert sum(w) == pytest.approx(1)
    assert w[2:] == pytest.approx([0.1, 0.1, 0.1])
    assert w[0] == pytest.approx(0.7 * 0.5 / 0.8)
    # Only one kind scored: it carries everything.
    assert share_weights([{"kind": "universal", "weight": 0.1}]) == [1.0]
    assert share_weights([{"kind": "role", "weight": 0.2}]) == [1.0]


def test_a_rambling_answer_now_loses_points_on_structure_and_clarity():
    def score(role, comms):
        cs = [
            CriterionScore(name="Objection handling", score=role),
            CriterionScore(name="Resilience", score=role),
            CriterionScore(name="Structure", score=comms),
            CriterionScore(name="Clarity", score=comms),
            CriterionScore(name="Relevance", score=comms),
        ]
        return weighted_score(cs, RUBRIC)[0]

    # Same content; the rambling one is poorly structured and unclear.
    assert score(4, 4) - score(4, 2) == pytest.approx(0.6)


def test_low_score_for_an_untested_skill_is_left_out():
    cs = [
        CriterionScore(
            name="Objection handling",
            score=2,
            comment="The candidate did not mention specific objections faced.",
        ),
        CriterionScore(
            name="Resilience", score=4, comment="Bounced back after losing the deal."
        ),
        CriterionScore(
            name="Structure", score=2, comment="Did not provide a clear structure."
        ),
    ]
    drop_untested(
        cs, RUBRIC, "Tell me about a time you showed resilience in your sales efforts."
    )
    assert cs[0].score is None and cs[0].comment == ""
    assert cs[1].score == 4
    assert cs[2].score == 2  # communication criteria always count


def test_low_score_stays_when_the_question_tests_the_skill():
    cs = [
        CriterionScore(
            name="Objection handling", score=2, comment="Did not address the objection."
        )
    ]
    drop_untested(cs, RUBRIC, "How do you handle a price objection from a CFO?")
    assert cs[0].score == 2
    # A low score with a real reason (not just "didn't mention") stays too.
    cs = [
        CriterionScore(
            name="Objection handling", score=2, comment="Argued with the buyer."
        )
    ]
    drop_untested(cs, RUBRIC, "Tell me about your resilience.")
    assert cs[0].score == 2


@pytest.mark.parametrize(
    "quote",
    [
        "I can’t recall the exact result.",
        "the outcome was still mixed",
        "Overall, it felt like a positive step forward for the relationship.",
        "which seemed to resonate well with them",
        "I guess it went fine in the end",
    ],
)
def test_words_without_an_outcome_are_not_a_result(quote):
    assert not states_outcome(quote)


@pytest.mark.parametrize(
    "quote",
    [
        "the client renewed for two more years",
        "They agreed to the trial and signed in March",
        "I can't recall exactly, but churn fell from 8% to 5%",
        "leadership approved the hourly reports",
    ],
)
def test_outcomes_are_results(quote):
    assert states_outcome(quote)


def _out(result_text, star_result=True):
    return ScoreOut.model_validate(
        {
            "criteria": [{"name": "Structure", "score": 2}],
            "summary": "s",
            "stronger_version": [{"text": "t", "source": None}],
            "said": {
                "situation": None,
                "task": None,
                "actions": [],
                "result": result_text,
                "other": [],
            },
            "missing_points": [
                {"point": "A measurable result or outcome", "covered": False}
            ],
            "star": {
                "situation": True,
                "task": False,
                "action": True,
                "result": star_result,
                "note": "",
            },
        }
    )


def test_a_quoted_non_result_does_not_count_as_the_star_result():
    answer = "We tried our best with the client. I can't recall the exact result."
    out = _out("I can't recall the exact result.")
    verify_coverage(out, [answer])
    assert out.star.result is False and out.star.result_quote is None
    assert out.missing_points[0].covered is False


def test_a_quoted_outcome_still_counts():
    answer = "I ran the discovery calls and the client renewed for two more years."
    out = _out("the client renewed for two more years", star_result=False)
    verify_coverage(out, [answer])
    assert out.star.result is True
    assert out.missing_points[0].covered is True
