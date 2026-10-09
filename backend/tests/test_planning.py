from types import SimpleNamespace

import pytest

from app.services.planning import JdAnalysisOut, normalize_minutes


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
