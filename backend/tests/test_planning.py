from types import SimpleNamespace

import pytest

from app.services.planning import (
    JdAnalysisOut,
    PlanSectionOut,
    enforce_hands_on,
    fit_counts,
    fit_hands_on,
    hands_on_limit,
    normalize_minutes,
)


def sections(*minutes):
    return [SimpleNamespace(minutes=m) for m in minutes]


@pytest.mark.parametrize(
    "minutes,duration",
    [
        ((5, 5), 10),
        ((3, 3, 3), 10),
        ((20, 20, 20), 30),
        ((1, 1, 1, 1), 60),
        ((50, 1), 5),
    ],
)
def test_minutes_sum_to_duration(minutes, duration):
    out = normalize_minutes(sections(*minutes), duration)
    assert sum(s.minutes for s in out) == duration
    assert all(s.minutes >= 1 for s in out)


def test_unknown_formats_are_dropped():
    out = JdAnalysisOut(
        role_title="x",
        field="x",
        seniority="mid",
        competencies=[{"name": "a"}],
        formats=["juggling", "case", "case"],
    )
    assert out.formats == ["case"]


LOOP = ["behavioral", "technical", "coding", "system_design"]


@pytest.mark.parametrize(
    "duration,kept",
    [
        (5, ["behavioral", "technical"]),  # T-81: a 5-minute plan got 2 min each
        (10, ["behavioral", "technical", "coding"]),
        (15, ["behavioral", "technical", "coding"]),
        (20, LOOP),
        (60, LOOP),
    ],
)
def test_hands_on_rounds_only_when_they_fit(duration, kept):
    assert fit_hands_on(LOOP, duration) == kept


def test_design_alone_needs_twelve_minutes():
    assert fit_hands_on(["behavioral", "system_design"], 11) == ["behavioral"]
    assert fit_hands_on(["behavioral", "system_design"], 12) == [
        "behavioral",
        "system_design",
    ]


def test_coding_problem_limits():
    assert hands_on_limit(5) == 0
    assert hands_on_limit(10) == 1
    assert hands_on_limit(30) == 3
    assert hands_on_limit(5, only=True) == 1  # a coding-only interview


def section(module, minutes, n=1):
    return PlanSectionOut(
        name=module,
        module=module,
        minutes=minutes,
        questions=[f"q{i}" for i in range(n)],
    )


def test_hands_on_sections_get_their_minimum_from_the_others():
    plan = [
        section("behavioral", 10),
        section("coding", 4),
        section("system_design", 6),
    ]
    out = enforce_hands_on(plan, 20)
    minutes = {s.module: s.minutes for s in out}
    assert minutes == {"behavioral": 2, "coding": 8, "system_design": 10}
    assert sum(minutes.values()) == 20


def test_coding_problems_that_cannot_fit_are_dropped():
    plan = [section("behavioral", 3), section("coding", 9, n=2)]
    out = enforce_hands_on(plan, 12)
    coding = next(s for s in out if s.module == "coding")
    assert len(coding.questions) == 1 and coding.minutes >= 8
    assert sum(s.minutes for s in out) == 12


def test_hands_on_sections_can_share_spare_time():
    # Only coding and design: design borrows coding's minutes above its 8.
    out = enforce_hands_on([section("coding", 12), section("system_design", 8)], 20)
    assert {s.module: s.minutes for s in out} == {"coding": 10, "system_design": 10}


@pytest.mark.parametrize(
    "duration,asked,got",
    [
        (60, (10, 2), (10, 2)),  # 40 + 10 of 58 spare minutes
        (30, (10, None), (7, None)),  # 28 // 4
        (30, (5, 10), (5, 1)),  # 28 - 20 = 8 → one design question
        (10, (0, 10), (0, 1)),
        (5, (3, None), (0, None)),
    ],
)
def test_chosen_counts_are_trimmed_to_fit(duration, asked, got):
    assert fit_counts(duration, *asked) == got


def test_a_coding_only_interview_always_gets_a_problem():
    assert fit_counts(5, 10, None, only=True) == (1, None)


def test_chosen_counts_use_the_shorter_floor_minutes():
    plan = [
        section("behavioral", 2),
        section("coding", 10, n=5),
        section("system_design", 6, n=2),
    ]
    out = enforce_hands_on(plan, 18, {"coding": 4, "system_design": 5})
    minutes = {s.module: s.minutes for s in out}
    assert minutes["coding"] >= 20 or len(out[1].questions) < 5
    assert sum(minutes.values()) == 18
