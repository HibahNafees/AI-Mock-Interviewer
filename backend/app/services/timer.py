"""The interview clock. It lives in the backend, never in the LLM."""

from dataclasses import asdict, dataclass
from datetime import datetime

from ..models import Question, Session
from ..models.base import utcnow

WRAP_UP_SEC = 60  # less than this left overall: wrap up
SECTION_NUDGE_SEC = 4 * 60  # tell the candidate when a section gets this close


@dataclass
class TimerState:
    total_sec: int
    elapsed_sec: int
    remaining_sec: int
    section: str | None
    section_budget_sec: int
    section_elapsed_sec: int
    section_remaining_sec: int
    paused: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def pauses(session: Session, now: datetime) -> list[tuple[datetime, datetime]]:
    """Pause spans; an open pause runs until now."""
    out = []
    for start, end in session.pauses_json or []:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end) if end else now
        out.append((a, b))
    return out


def is_paused(session: Session) -> bool:
    return bool(session.pauses_json) and session.pauses_json[-1][1] is None


def _active_secs(
    later: datetime, earlier: datetime | None, spans: list[tuple[datetime, datetime]]
) -> int:
    """Seconds between the two, minus any time spent paused."""
    if earlier is None:
        return 0
    paused = sum(
        max(0.0, (min(b, later) - max(a, earlier)).total_seconds()) for a, b in spans
    )
    return max(0, int((later - earlier).total_seconds() - paused))


def timer_state(
    session: Session, asked: list[Question], now: datetime | None = None
) -> TimerState:
    """Overall and current-section time. `asked` = asked questions, oldest first."""
    now = now or utcnow()
    total = session.duration_min * 60
    end = session.ended_at or now
    spans = pauses(session, end)
    elapsed = min(total, _active_secs(end, session.started_at, spans))
    # The ice-breaker isn't part of any section of the plan.
    asked = [q for q in asked if not (q.is_icebreaker or q.is_candidate_qa)]
    section = asked[-1].section if asked else None
    minutes = {
        s["name"]: s["minutes"] for s in (session.plan_json or {}).get("sections", [])
    }
    budget = minutes.get(section, 0) * 60 if section else 0
    first_in_section = next((q.asked_at for q in asked if q.section == section), None)
    section_elapsed = _active_secs(end, first_in_section, spans)
    return TimerState(
        total_sec=total,
        elapsed_sec=elapsed,
        remaining_sec=total - elapsed,
        section=section,
        section_budget_sec=budget,
        section_elapsed_sec=section_elapsed,
        section_remaining_sec=budget - section_elapsed,
        paused=is_paused(session),
    )
