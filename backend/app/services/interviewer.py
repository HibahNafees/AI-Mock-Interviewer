"""Interviewer turns: what to ask next, given the plan, the clock and the last answer.

The backend decides which moves are allowed (follow up, next question, bonus,
wrap up) from the timer; Fire chat only picks among them and words the reply.
"""

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from .. import modules
from ..extensions import db
from ..models import Answer, Question, Session
from ..models.base import utcnow
from .llm import chat_json, render
from .timer import SECTION_NUDGE_SEC, WRAP_UP_SEC, TimerState, timer_state

log = logging.getLogger(__name__)

MAX_FOLLOW_UPS = 2
# A role-play is a conversation: the character's replies are follow-ups.
MAX_ROLEPLAY_TURNS = 6
HISTORY_TURNS = 8
BONUS_MIN_SEC = 3 * 60

PERSONAS = {
    "friendly": "warm and encouraging; you put the candidate at ease",
    "neutral": "professional and even-toned",
    "tough": "direct and demanding; you probe hard but always stay respectful",
}

OPENINGS = {
    "friendly": "Hi {name}, thanks for joining! This is a {minutes}-minute interview for "
    "the {role} role. I'll keep an eye on the clock, so just focus on your answers. "
    "Let's begin.",
    "neutral": "Hello {name}. This is a {minutes}-minute interview for the {role} role. "
    "I'll keep track of time. Let's begin.",
    "tough": "Hello {name}. We have {minutes} minutes for the {role} role, so let's make "
    "them count. First question.",
}

CLOSING = (
    "That's all the time we have. Thank you for your answers today; "
    "that's the end of the interview."
)
CLOSING_EARLY = (
    "That covers everything I wanted to ask. Thank you for your answers today; "
    "that's the end of the interview."
)


# Evaluative words the interviewer must not use about an answer (feedback is for the
# report). Applied only to statements; questions like "What was the most interesting
# part?" are kept.
PRAISE_RE = re.compile(
    r"\b(great|good|solid|interesting|impressive|excellent|nice|fantastic|awesome|"
    r"wonderful|insight|insightful|strong|perfect|well done|well said|sounds like|"
    r"love that|appreciate (?:your|the) (?:thoughts|insights?|answer|perspective)|"
    r"thanks for (?:that|the|your) (?:insight|great|detailed|thorough))",
    re.IGNORECASE,
)
SENTENCE_RE = re.compile(r"[^.!?]+[.!?]*\s*")


PROMPT_RE = re.compile(
    r"\s*(tell|walk|describe|explain|give|share|talk|show|take)\b", re.IGNORECASE
)


def _is_question(sentence: str) -> bool:
    return "?" in sentence or bool(PROMPT_RE.match(sentence))


def neutralize(message: str) -> str:
    """Drop statements that praise or grade the answer; keep the question(s)."""
    sentences = SENTENCE_RE.findall(message)
    kept, dropped = [], False
    for i, sentence in enumerate(sentences):
        last = i == len(sentences) - 1
        if not last and not _is_question(sentence) and PRAISE_RE.search(sentence):
            dropped = True
            continue
        kept.append(sentence)
    if not dropped:
        return message
    out = "".join(kept).strip()
    # A contrast word only made sense after the sentence we removed.
    out = re.sub(
        r"(^|[.!?]\s+)(however|but),\s*(\w)",
        lambda m: m[1] + m[3].upper(),
        out,
        flags=re.I,
    )
    starts_with_ack = re.match(
        r"(thanks|thank you|okay|ok|got it|understood|right)\b", out, re.I
    )
    return out if starts_with_ack else f"Thanks. {out}"


ROLEPLAY_EXIT = "Let's step out of the role-play there."


def section_info(session: Session, name: str | None) -> dict:
    for s in (session.plan_json or {}).get("sections", []):
        if s["name"] == name:
            return s
    return {}


def scenario_of(session: Session, section: str | None) -> dict | None:
    info = section_info(session, section)
    return info.get("scenario") if info.get("module") == "roleplay" else None


def roleplay_intro(scenario: dict) -> str:
    """Said by the app (not the model) so the switch into character is always clear."""
    setting = scenario.get("setting", "").strip()
    parts = [
        "Let's switch to a role-play.",
        f"I'll play {scenario['character'].strip().rstrip('.')}.",
        f"Setting: {setting.rstrip('.')}." if setting else "",
        f"Your goal: {scenario['goal'].strip().rstrip('.')}.",
        "I'm in character from now on.",
    ]
    return " ".join(p for p in parts if p)


def _entering(session: Session, question: Question, previous: Question | None) -> str:
    """The role-play intro if `question` opens a role-play section, else ""."""
    scenario = scenario_of(session, question.section)
    if scenario is None or (
        previous is not None and previous.section == question.section
    ):
        return ""
    return roleplay_intro(scenario) + " "


class TurnOut(BaseModel):
    action: Literal["follow_up", "next_question", "bonus", "wrap_up"]
    message: str = Field(min_length=1, max_length=1500)


def asked_questions(session: Session) -> list[Question]:
    return list(
        db.session.scalars(
            db.select(Question)
            .filter_by(session_id=session.id)
            .where(Question.asked_at.is_not(None))
            .order_by(Question.asked_at, Question.id)
        )
    )


def _ask(question: Question, message: str) -> None:
    question.asked_at = utcnow()
    question.asked_text = message


def start(session: Session, user_name: str) -> Question:
    """Start the clock and ask the first planned question."""
    first = db.session.scalar(
        db.select(Question)
        .filter_by(session_id=session.id, is_bonus=False, follow_up_of_id=None)
        .order_by(Question.order_no)
    )
    if first is None:
        raise ValueError("The plan has no questions")
    session.status = "active"
    session.started_at = utcnow()
    opening = OPENINGS.get(session.persona or "neutral", OPENINGS["neutral"]).format(
        name=user_name,
        minutes=session.duration_min,
        role=(session.plan_json or {}).get("role_title") or "this",
    )
    _ask(first, f"{opening} {_entering(session, first, None)}{first.text}")
    db.session.commit()
    return first


def _section_order(session: Session) -> list[str]:
    return [s["name"] for s in (session.plan_json or {}).get("sections", [])]


def options(session: Session, asked: list[Question], timer: TimerState) -> dict:
    """The moves the interviewer may make next, with the candidate questions."""
    if timer.remaining_sec <= WRAP_UP_SEC:
        return {"wrap_up": None}

    current = asked[-1]
    root = current
    if current.follow_up_of_id:
        root = db.session.get(Question, current.follow_up_of_id) or current
    follow_ups = sum(1 for q in asked if q.follow_up_of_id == root.id)
    in_roleplay = scenario_of(session, root.section) is not None
    max_follow_ups = MAX_ROLEPLAY_TURNS if in_roleplay else MAX_FOLLOW_UPS

    order = _section_order(session)
    here = order.index(root.section) if root.section in order else 0
    min_section = here + 1 if timer.section_remaining_sec <= 0 else here
    unasked = db.session.scalars(
        db.select(Question)
        .filter_by(session_id=session.id, follow_up_of_id=None)
        .where(Question.asked_at.is_(None))
        .order_by(Question.order_no)
    ).all()
    next_q = next(
        (
            q
            for q in unasked
            if not q.is_bonus
            and (order.index(q.section) if q.section in order else 0) >= min_section
        ),
        None,
    )
    bonus = next((q for q in unasked if q.is_bonus), None)

    opts: dict[str, Question | None] = {}
    if (
        follow_ups < max_follow_ups
        and timer.section_remaining_sec > (30 if in_roleplay else 90)
        and timer.remaining_sec > 2 * 60
    ):
        opts["follow_up"] = None
    if next_q:
        opts["next_question"] = next_q
    elif bonus and timer.remaining_sec > BONUS_MIN_SEC:
        opts["bonus"] = bonus
    if not next_q:
        opts["wrap_up"] = None
    return opts


def nudges(
    timer: TimerState,
    options_: dict,
    root_budget: int | None,
    answer_sec: float,
    in_roleplay: bool = False,
):
    if in_roleplay:
        return []  # Time and length notes would break character.
    notes = []
    next_q = options_.get("next_question")
    if (
        next_q is not None
        and next_q.section == timer.section
        and 0 < timer.section_remaining_sec <= SECTION_NUDGE_SEC
    ):
        mins = max(1, round(timer.section_remaining_sec / 60))
        notes.append(f"Mention there are about {mins} minutes left in this section.")
    if next_q is not None and next_q.section != timer.section:
        notes.append(
            f'Signal that you are moving on to a new part: "{next_q.section}".'
        )
    if root_budget and root_budget >= 60 and answer_sec > root_budget * 1.5:
        notes.append(
            "That answer ran long; politely ask them to keep the next one tighter."
        )
    return notes


def _history(asked: list[Question]) -> list[dict]:
    ids = [q.id for q in asked[-HISTORY_TURNS:]]
    answers = {
        a.question_id: a.transcript
        for a in db.session.scalars(
            db.select(Answer).where(Answer.question_id.in_(ids)).filter_by(attempt_no=1)
        )
    }
    return [
        {
            "interviewer": (q.asked_text or q.text)[:800],
            "candidate": answers.get(q.id, "")[:1500],
        }
        for q in asked[-HISTORY_TURNS:]
    ]


def take_turn(
    session: Session,
    user_id: int,
    text: str,
    duration_ms: int | None,
    input_mode: str = "text",
) -> dict:
    """Save the answer to the current question and produce the interviewer's reply."""
    asked = asked_questions(session)
    current = asked[-1]
    timer = timer_state(session, asked)
    opts = options(session, asked, timer)

    root_budget = current.budget_sec
    if current.follow_up_of_id:
        root = db.session.get(Question, current.follow_up_of_id)
        root_budget = root.budget_sec if root else None
    answer_sec = (duration_ms or 0) / 1000

    scenario = scenario_of(session, current.section)
    module = section_info(session, current.section).get("module", modules.DEFAULT)
    if list(opts) == ["wrap_up"]:
        closing = CLOSING if timer.remaining_sec <= WRAP_UP_SEC else CLOSING_EARLY
        out = TurnOut(action="wrap_up", message=closing)
    else:
        choices = {
            name: (q.text if q is not None else None) for name, q in opts.items()
        }
        common = dict(
            difficulty=session.difficulty or "mid",
            role=(session.plan_json or {}).get("role_title") or "the role",
            current_question=current.asked_text or current.text,
            answer=text,
            minutes_left=str(max(0, round(timer.remaining_sec / 60))),
            choices=choices,
            module_guidance=modules.guidance(module, "interview"),
        )
        if scenario is not None:
            root_id = current.follow_up_of_id or current.id
            prompt = render(
                "roleplay_turn",
                scenario=scenario,
                history=_history(
                    [q for q in asked[:-1] if (q.follow_up_of_id or q.id) == root_id]
                ),
                **common,
            )
        else:
            prompt = render(
                "interviewer_turn",
                persona=PERSONAS.get(session.persona or "neutral", PERSONAS["neutral"]),
                history=_history(asked[:-1]),
                section=timer.section or "",
                nudges=nudges(timer, opts, root_budget, answer_sec) or ["none"],
                **common,
            )
        out = chat_json(user_id, prompt, TurnOut, max_tokens=500, temperature=0.6)
        if not (scenario is not None and out.action == "follow_up"):
            # In character, praise or agreement is part of the role-play.
            out.message = neutralize(out.message)
        if out.action not in opts:
            log.info("Interviewer chose %s; allowed %s", out.action, list(opts))
            out = _fallback(opts)

    if out.action != "follow_up":
        nxt = opts.get(out.action) if out.action in ("next_question", "bonus") else None
        leaving = scenario is not None and (
            nxt is None or nxt.section != current.section
        )
        entering = _entering(session, nxt, current) if nxt is not None else ""
        if entering:
            # The character's opening line is used as planned, after the intro.
            lead = ROLEPLAY_EXIT if leaving else "Thanks."
            out.message = f"{lead} {entering}{nxt.text}"
        elif leaving:
            out.message = f"{ROLEPLAY_EXIT} {out.message}"

    now = utcnow()
    ended_ms = int((now - session.started_at).total_seconds() * 1000)
    started_ms = max(0, ended_ms - duration_ms) if duration_ms else None
    answer = Answer(
        question_id=current.id,
        transcript=text,
        started_ms=started_ms,
        ended_ms=ended_ms,
        duration_ms=duration_ms,
        attempt_no=1,
        input_mode=input_mode,
    )
    db.session.add(answer)

    if out.action == "follow_up":
        root_id = current.follow_up_of_id or current.id
        follow = Question(
            session_id=session.id,
            section=current.section,
            order_no=current.order_no,
            text=out.message,
            budget_sec=120,
            is_bonus=False,
            follow_up_of_id=root_id,
        )
        _ask(follow, out.message)
        db.session.add(follow)
    elif out.action in ("next_question", "bonus"):
        _ask(opts[out.action], out.message)
    else:
        session.status = "completed"
        session.ended_at = now
    db.session.commit()
    return {"action": out.action, "message": out.message}


def _fallback(opts: dict) -> TurnOut:
    """Used when the model picks a move the clock doesn't allow."""
    for action in ("next_question", "bonus"):
        q = opts.get(action)
        if q is not None:
            return TurnOut(action=action, message=f"Thank you. Next question: {q.text}")
    return TurnOut(action="wrap_up", message=CLOSING_EARLY)


def end(session: Session) -> None:
    session.status = "completed"
    session.ended_at = utcnow()
    db.session.commit()
