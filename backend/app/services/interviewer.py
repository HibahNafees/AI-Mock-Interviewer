"""Interviewer turns: what to ask next, given the plan, the clock and the last answer.

The backend decides which moves are allowed (follow up, next question, bonus,
wrap up) from the timer; Fire chat only picks among them and words the reply.
"""

import logging
import random
import re
from typing import Literal

from flask import current_app
from pydantic import BaseModel, Field

from .. import modules
from ..extensions import db
from ..models import Answer, Document, Question, Session, User
from ..models.base import utcnow
from .fire import FireError
from .limits import LimitReached
from .llm import chat_json, render
from . import negotiation, panel, pressure
from .work import HISTORY_CHARS, with_work
from .timer import SECTION_NUDGE_SEC, WRAP_UP_SEC, TimerState, is_paused, timer_state

log = logging.getLogger(__name__)

MAX_FOLLOW_UPS = 2
# A role-play is a conversation: the character's replies are follow-ups.
MAX_ROLEPLAY_TURNS = 6
HISTORY_TURNS = 8
BONUS_MIN_SEC = 3 * 60
MAX_JD_CHARS = 4000

# How each interviewer sounds (T-97: one short phrase each made all three alike).
PERSONAS = {
    "friendly": (
        "warm and encouraging; you put the candidate at ease. Sound like a kind "
        'colleague: frame follow-ups gently ("I\'d love to hear a bit more about..."), '
        'and if they struggle, reassure them ("Take your time.") before asking'
    ),
    "neutral": "professional and even-toned: plain questions, no warmth and no pressure",
    "tough": (
        "direct and demanding, but always respectful. No pleasantries. Probe hard: "
        "ask for the exact number, their own part rather than the team's, why they "
        "chose that over an alternative, or what went wrong. When an answer is vague, "
        'say so in a few words before your question ("That\'s still general.")'
    ),
}
# How a reply may open, per persona; pressure mode opens like "tough".
OPENING_RULES = {
    "friendly": (
        "Start with a short, warm acknowledgement that doesn't judge the answer, such "
        'as "Thanks for walking me through that." or "Okay, that helps."'
    ),
    "neutral": (
        'Start with at most a neutral acknowledgement such as "Thanks.", '
        '"Okay.", "Got it." or "Understood."'
    ),
    "tough": (
        "Don't thank them or acknowledge the answer: go straight to your question, or "
        "first say in a few words what was missing (\"You said 'we'. What did you do?\")"
    ),
}
# What the level means for follow-ups (T-97: difficulty only shaped the plan).
DIFFICULTY_RULES = {
    "entry": "Entry level: keep follow-ups plain and one step at a time, about fundamentals and how they learn; don't expect senior-level scope.",
    "mid": "Mid level: probe ownership and depth: what they did themselves, how, and what came of it.",
    "senior": "Senior level: probe scope, trade-offs, scale, risk and how they led others; expect precise reasoning.",
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

# With an ice-breaker, the greeting leads into it instead of "Let's begin."
GREETINGS = {
    "friendly": "Hi {name}, thanks for joining! This is a {minutes}-minute interview for "
    "the {role} role, and I'll keep an eye on the clock. Before we dive in: {ice}",
    "neutral": "Hello {name}, nice to meet you. This is a {minutes}-minute interview for "
    "the {role} role; I'll keep track of time. To start: {ice}",
    "tough": "Hello {name}. We have {minutes} minutes for the {role} role. Quickly, "
    "before we start: {ice}",
}
ICEBREAKERS = [
    "How are you doing today?",
    "How's your day going so far?",
    "Tell me a little about yourself.",
    "What's something you've enjoyed working on recently?",
    "What got you interested in this role?",
    "How are you feeling about today's interview?",
]
ICEBREAKER_SECTION = "Ice-breaker"
PANEL_GREETING = (
    "Hello {name}, thanks for joining. This is a {minutes}-minute panel interview for "
    "the {role} role. {panel} Before we dive in: {ice}"
)
PANEL_OPENING = (
    "Hello {name}, thanks for joining. This is a {minutes}-minute panel interview for "
    "the {role} role. {panel} Let's begin."
)
INTO_PLAN = {
    "friendly": "Let's get started.",
    "neutral": "Let's get started.",
    "tough": "Let's get to it.",
}
ICEBREAKER_FALLBACK = "Thanks for sharing."

# How the interviewer signs off; one is picked per session.
CLOSINGS = [
    "That's everything from me, {name}. It was really great talking with you today. "
    "The team will review everything, and you'll hear back by email about next steps. "
    "Take care!",
    "Thank you so much for your time, {name}; I really enjoyed our conversation. "
    "We'll be in touch by email soon about next steps. Have a great rest of your day!",
    "That brings us to the end. It was a pleasure speaking with you, {name}. You'll get "
    "an email from us once the team has made a decision. Best of luck!",
]
TOUGH_CLOSING = (
    "That's everything, {name}. Thanks for your time. You'll hear back from us by "
    "email."
)
OUT_OF_TIME = "Looks like we're out of time."
NEGOTIATION_CLOSING = (
    "That's the end of the negotiation practice, {name}. Your report shows how you did "
    "on anchoring, justifying your number and staying calm."
)

# The candidate's turn to ask (not scored): asked instead of signing off.
QA_SECTION = "Your questions"
INVITE = "Before we wrap up, do you have any questions for me?"
INVITE_LATE = (
    "We're nearly out of time, but before we finish: do you have any questions for me?"
)
ANYTHING_ELSE = "Is there anything else you'd like to know?"
MAX_CANDIDATE_QUESTIONS = 3


def closing(session: Session, out_of_time: bool = False) -> str:
    """A natural sign-off, the same one for the whole session."""
    user = db.session.get(User, session.user_id)
    name = (user.name if user else "").split(" ")[0] or "there"
    if session.mode == "negotiation":
        # The recruiter already said goodbye in character (T-57).
        text = NEGOTIATION_CLOSING.format(name=name)
    elif session.persona == "tough":
        text = TOUGH_CLOSING.format(name=name)
    else:
        text = random.Random(session.id).choice(CLOSINGS).format(name=name)
    return f"{OUT_OF_TIME} {text}" if out_of_time else text


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


def neutralize(message: str, plain: bool = False) -> str:
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
    # A tough or pressure interviewer doesn't say thanks (T-97).
    return out if starts_with_ack or plain else f"Thanks. {out}"


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
    return roleplay_intro(scenario)


INTERVIEWER, CHARACTER = "interviewer", "character"


def _segments(parts: list[tuple]) -> list[dict]:
    """[(who, text[, panelist])] → [{"who", "text"[, "panelist"]}], dropping blanks
    and joining same-speaker runs.

    Lets the browser voice the interviewer, a role-play character and each panel
    interviewer differently.
    """
    out: list[dict] = []
    for who, text, *rest in parts:
        text = text.strip()
        key = rest[0] if rest and who == INTERVIEWER else None
        if not text:
            continue
        if out and out[-1]["who"] == who and out[-1].get("panelist") == key:
            out[-1]["text"] += f" {text}"
        else:
            out.append({"who": who, "text": text, **({"panelist": key} if key else {})})
    return out


def _by(session: Session, key: str | None, parts: list[tuple]) -> list[tuple]:
    """Panel: the interviewer lines in `parts` without a speaker are `key`'s."""
    if session.mode != "panel" or key is None:
        return parts
    return [p if len(p) > 2 else (*p, key) for p in parts]


def _handover(
    session: Session, from_key: str | None, nxt: Question | None, first: bool = False
) -> list[tuple]:
    """Panel: the outgoing interviewer hands over when `nxt` belongs to someone else."""
    to_key = panel.owner(session, nxt.section) if nxt is not None else None
    if to_key is None or to_key == from_key:
        return []
    bye, hello = panel.handover(to_key, first)
    return [(INTERVIEWER, bye, from_key or panel.LEAD), (INTERVIEWER, hello, to_key)]


def _persona(session: Session, section: str | None) -> str:
    text = PERSONAS.get(session.persona or "neutral", PERSONAS["neutral"])
    key = panel.owner(session, section)
    return f"{text}. {panel.persona_note(key, session)}" if key else text


def _speaker_of(session: Session, question: Question) -> str:
    """A planned role-play question is the character's opening line."""
    in_roleplay = not question.is_bonus and scenario_of(session, question.section)
    return CHARACTER if in_roleplay else INTERVIEWER


class TurnOut(BaseModel):
    action: Literal["follow_up", "next_question", "bonus", "wrap_up"]
    message: str = Field(min_length=1, max_length=1500)


EXITS = ("next_question", "bonus", "wrap_up")


class RoleplayTurnOut(TurnOut):
    # Asked for first so the character decides before it writes (T-21: without it,
    # the character kept inventing new objections and never accepted a next step).
    goal_reached: bool = False


def asked_questions(session: Session) -> list[Question]:
    return list(
        db.session.scalars(
            db.select(Question)
            .filter_by(session_id=session.id)
            .where(Question.asked_at.is_not(None))
            .order_by(Question.asked_at, Question.id)
        )
    )


def _ask(question: Question, segments: list[dict]) -> None:
    question.asked_at = utcnow()
    question.asked_text = " ".join(s["text"] for s in segments)
    question.asked_segments = segments


def start(session: Session, user_name: str) -> Question:
    """Start the clock and ask the ice-breaker (or the first planned question)."""
    first = db.session.scalar(
        db.select(Question)
        .filter_by(
            session_id=session.id,
            is_bonus=False,
            is_icebreaker=False,
            follow_up_of_id=None,
        )
        .order_by(Question.order_no)
    )
    if first is None:
        raise ValueError("The plan has no questions")
    session.status = "active"
    session.started_at = utcnow()
    first_by = panel.owner(session, first.section)
    if session.mode == "negotiation":
        # Straight into the call: no small talk, no "interview" opening.
        _ask(
            first,
            _segments(
                [
                    (INTERVIEWER, negotiation.intro(session)),
                    (INTERVIEWER, _entering(session, first, None)),
                    (CHARACTER, first.text),
                ]
            ),
        )
        db.session.commit()
        return first
    if current_app.config.get("ICEBREAKER", True):
        ice = Question(
            session_id=session.id,
            section=ICEBREAKER_SECTION,
            order_no=0,
            text=random.Random(session.id).choice(ICEBREAKERS),
            budget_sec=60,
            is_bonus=False,
            is_icebreaker=True,
        )
        db.session.add(ice)
        greeting = (
            PANEL_GREETING
            if session.mode == "panel"
            else GREETINGS.get(session.persona or "neutral", GREETINGS["neutral"])
        )
        _ask(
            ice,
            _segments(
                _by(
                    session,
                    panel.LEAD,
                    [
                        (
                            INTERVIEWER,
                            greeting.format(
                                name=user_name.split(" ")[0],
                                minutes=session.duration_min,
                                role=(session.plan_json or {}).get("role_title")
                                or "this",
                                ice=ice.text,
                                panel=(
                                    panel.introductions(session)
                                    if session.mode == "panel"
                                    else ""
                                ),
                            ),
                        )
                    ],
                )
            ),
        )
        db.session.commit()
        return ice
    opening = (
        PANEL_OPENING
        if session.mode == "panel"
        else OPENINGS.get(session.persona or "neutral", OPENINGS["neutral"])
    ).format(
        name=user_name,
        minutes=session.duration_min,
        role=(session.plan_json or {}).get("role_title") or "this",
        panel=panel.introductions(session) if session.mode == "panel" else "",
    )
    _ask(
        first,
        _segments(
            [
                *_by(session, panel.LEAD, [(INTERVIEWER, opening)]),
                *_handover(session, panel.LEAD, first, first=True),
                *_by(
                    session,
                    first_by,
                    [
                        (INTERVIEWER, _entering(session, first, None)),
                        (_speaker_of(session, first), first.text),
                        *_time_note(session, first),
                    ],
                ),
            ]
        ),
    )
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
    max_follow_ups = (
        negotiation.MAX_TURNS
        if session.mode == "negotiation"
        else MAX_ROLEPLAY_TURNS if in_roleplay else MAX_FOLLOW_UPS
    )

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
    # A reserve question is the interviewer's, never a character line (T-26: in a
    # role-play section it re-entered the role-play as the character).
    bonus = next(
        (q for q in unasked if q.is_bonus and scenario_of(session, q.section) is None),
        None,
    )

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
        a.question_id: with_work(a.transcript[:1500], a.work_json)[
            : 1500 + HISTORY_CHARS
        ]
        for a in db.session.scalars(
            db.select(Answer).where(Answer.question_id.in_(ids)).filter_by(attempt_no=1)
        )
    }
    return [
        {
            "interviewer": (q.asked_text or q.text)[:800],
            "candidate": answers.get(q.id, ""),
        }
        for q in asked[-HISTORY_TURNS:]
    ]


def take_turn(
    session: Session,
    user_id: int,
    text: str,
    duration_ms: int | None,
    input_mode: str = "text",
    work: dict | None = None,
    body: dict | None = None,
) -> dict:
    """Save the answer to the current question and produce the interviewer's reply."""
    asked = asked_questions(session)
    current = asked[-1]
    if current.is_icebreaker:
        return _after_icebreaker(
            session, user_id, current, text, duration_ms, input_mode
        )
    if current.is_candidate_qa:
        return _after_candidate_question(
            session, user_id, asked, current, text, duration_ms, input_mode
        )
    timer = timer_state(session, asked)
    # A negotiation ends with the call, not "any questions for me?".
    invite = (
        current_app.config.get("CANDIDATE_QUESTIONS", True)
        and session.mode != "negotiation"
    )

    def sign_off(out_of_time: bool = False) -> str:
        """Invite the candidate's questions, or close if that's switched off."""
        if invite:
            return INVITE_LATE if out_of_time else INVITE
        return closing(session, out_of_time)

    opts = options(session, asked, timer)

    root_budget = current.budget_sec
    if current.follow_up_of_id:
        root = db.session.get(Question, current.follow_up_of_id)
        root_budget = root.budget_sec if root else None
    answer_sec = (duration_ms or 0) / 1000

    scenario = scenario_of(session, current.section)
    fell_back = False
    in_character = False  # out.message is the role-play character's line
    module = section_info(session, current.section).get("module", modules.DEFAULT)
    if list(opts) == ["wrap_up"]:
        out = TurnOut(
            action="wrap_up",
            message=sign_off(out_of_time=timer.remaining_sec <= WRAP_UP_SEC),
        )
    else:
        choices = {
            name: (q.text if q is not None and scenario is None else None)
            for name, q in opts.items()
        }
        common = dict(
            difficulty=session.difficulty or "mid",
            role=(session.plan_json or {}).get("role_title") or "the role",
            current_question=current.asked_text or current.text,
            answer=with_work(text, work),
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
            tough = session.persona == "tough" or bool(session.pressure_level)
            prompt = render(
                "interviewer_turn",
                persona=_persona(session, current.section),
                opening_rule=OPENING_RULES[
                    "tough" if tough else session.persona or "neutral"
                ],
                difficulty_rule=DIFFICULTY_RULES.get(
                    session.difficulty or "mid", DIFFICULTY_RULES["mid"]
                ),
                pressure=(
                    "\n".join(
                        f"- {n}" for n in pressure.notes(session.pressure_level or 0)
                    )
                    if session.pressure_level
                    else "none"
                ),
                history=_history(asked[:-1]),
                asked_follow_ups=[
                    q.asked_text or q.text
                    for q in asked
                    if q.follow_up_of_id == (current.follow_up_of_id or current.id)
                ]
                or "none",
                section=timer.section or "",
                nudges=nudges(timer, opts, root_budget, answer_sec) or ["none"],
                **common,
            )
        schema = TurnOut if scenario is None else RoleplayTurnOut
        out = chat_json(user_id, prompt, schema, max_tokens=500, temperature=0.6)
        if scenario is not None and (
            getattr(out, "goal_reached", False) or out.action != "follow_up"
        ):
            # The character's reply is its goodbye, whichever way the clock lets the
            # interview go on (T-21: goal reached; T-26: an exit that isn't allowed).
            if out.action == "follow_up" or out.action not in opts:
                # options() always offers next_question or wrap_up.
                out.action = next(a for a in EXITS if a in opts)
        if scenario is None:
            # In character, praise or agreement is part of the role-play.
            out.message = neutralize(
                out.message,
                plain=session.persona == "tough" or bool(session.pressure_level),
            )
        if out.action not in opts:
            log.info("Interviewer chose %s; allowed %s", out.action, list(opts))
            out = _fallback(opts, sign_off())
            fell_back = True
        elif scenario is None and out.action == "follow_up":
            root_id = current.follow_up_of_id or current.id
            earlier = [
                q.asked_text or q.text for q in asked if q.follow_up_of_id == root_id
            ]
            if any(_same_question(out.message, e) for e in earlier):
                # The candidate didn't answer it the first time: move on (T-44).
                log.info("Repeated follow-up; moving on")
                out = _fallback(
                    {k: v for k, v in opts.items() if k != "follow_up"}, sign_off()
                )
                fell_back = True
        in_character = scenario is not None and not fell_back

    said = (CHARACTER if in_character else INTERVIEWER, out.message)
    parts = [said]
    if out.action != "follow_up":
        nxt = opts.get(out.action) if out.action in ("next_question", "bonus") else None
        leaving = scenario is not None and (
            nxt is None or nxt.section != current.section
        )
        entering = _entering(session, nxt, current) if nxt is not None else ""
        if scenario is not None and nxt is not None:
            # The character never sees the next planned question (it blended the next
            # scenario into its replies, live check T-25): its closing line, then the
            # app steps out and asks the question as planned.
            parts = ([said] if in_character else []) + [
                (INTERVIEWER, ROLEPLAY_EXIT),
                (INTERVIEWER, entering),
                (_speaker_of(session, nxt), nxt.text),
            ]
        elif entering:
            # The character's opening line is used as planned, after the intro.
            parts = [
                (INTERVIEWER, "Thanks."),
                (INTERVIEWER, entering),
                (CHARACTER, nxt.text),
            ]
        elif leaving and in_character:
            # The character's goodbye, then the app steps out and closes.
            parts = [
                said,
                (INTERVIEWER, ROLEPLAY_EXIT),
                (INTERVIEWER, sign_off()),
            ]
        elif leaving:
            parts = [(INTERVIEWER, ROLEPLAY_EXIT), said]
        elif out.action == "wrap_up" and not fell_back and list(opts) != ["wrap_up"]:
            # The app's natural sign-off, not the model's one-line thank-you.
            parts = [(INTERVIEWER, sign_off())]
    if out.action in ("next_question", "bonus"):
        parts += _time_note(session, opts.get(out.action))
    cur_by = panel.owner(session, current.section)
    if session.mode == "panel":
        nxt = opts.get(out.action) if out.action in ("next_question", "bonus") else None
        hand = _handover(session, cur_by, nxt)
        if hand:
            # Someone else asks next: they open with the question as planned (the
            # model worded it in the current interviewer's voice).
            lead_in = [said] if in_character else []
            if scenario is not None:
                lead_in.append((INTERVIEWER, ROLEPLAY_EXIT))
            to_by = hand[-1][2]
            parts = (
                _by(session, cur_by, lead_in)
                + hand
                + _by(
                    session,
                    to_by,
                    [
                        (INTERVIEWER, _entering(session, nxt, current)),
                        (_speaker_of(session, nxt), nxt.text),
                        *_time_note(session, nxt),
                    ],
                )
            )
        else:
            # The app's sign-off and invitation come from the lead interviewer.
            parts = _by(
                session, panel.LEAD if out.action == "wrap_up" else cur_by, parts
            )
    segments = _segments(parts)
    out.message = " ".join(s["text"] for s in segments)

    now = _save_answer(session, current, text, duration_ms, input_mode, work, body)

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
        _ask(follow, segments)
        db.session.add(follow)
    elif out.action in ("next_question", "bonus"):
        _ask(opts[out.action], segments)
    elif invite:
        # Not the end yet: the candidate's turn to ask.
        qa = _qa_question(session, current, INVITE)
        _ask(qa, segments)
        db.session.commit()
        return {
            "action": "your_questions",
            "message": out.message,
            "segments": segments,
        }
    else:
        session.status = "completed"
        session.ended_at = now
    db.session.commit()
    return {"action": out.action, "message": out.message, "segments": segments}


def _save_answer(
    session: Session,
    question: Question,
    text: str,
    duration_ms: int | None,
    input_mode: str,
    work: dict | None = None,
    body: dict | None = None,
):
    now = utcnow()
    ended_ms = int((now - session.started_at).total_seconds() * 1000)
    started_ms = max(0, ended_ms - duration_ms) if duration_ms else None
    db.session.add(
        Answer(
            question_id=question.id,
            transcript=text,
            started_ms=started_ms,
            ended_ms=ended_ms,
            duration_ms=duration_ms,
            attempt_no=1,
            input_mode=input_mode,
            work_json=work,
            body_json=body,
        )
    )
    return now


class IcebreakerReply(BaseModel):
    message: str = Field(min_length=1, max_length=300)


# The app adds its own "Let's get started." after the reply; any "let's ..." in small
# talk is a transition to the questions (T-98).
INTO_PLAN_RE = re.compile(
    r"\s*((now|so|okay|ok|alright),?\s*)?let'?s\b",
    re.IGNORECASE,
)


def tidy_small_talk(reply: str) -> str:
    """Drop questions and "let's get started" lines from the ice-breaker reply,
    which the model adds despite the prompt; the first question follows it (T-98).
    """
    kept = [
        s
        for s in SENTENCE_RE.findall(reply)
        if "?" not in s and not INTO_PLAN_RE.match(s)
    ]
    return "".join(kept).strip() or ICEBREAKER_FALLBACK


def _after_icebreaker(
    session: Session,
    user_id: int,
    ice: Question,
    text: str,
    duration_ms: int | None,
    input_mode: str,
) -> dict:
    """A warm one-line reply to the small talk, then the first planned question."""
    first = db.session.scalar(
        db.select(Question)
        .filter_by(
            session_id=session.id,
            is_bonus=False,
            is_icebreaker=False,
            follow_up_of_id=None,
        )
        .order_by(Question.order_no)
    )
    try:
        reply = chat_json(
            user_id,
            render(
                "icebreaker_reply",
                persona=_persona(session, None),
                question=ice.text,
                answer=text,
            ),
            IcebreakerReply,
            max_tokens=120,
            temperature=0.7,
        ).message
        reply = tidy_small_talk(reply)
    except (FireError, LimitReached) as err:
        # Small talk isn't worth failing the turn over.
        log.warning("Ice-breaker reply failed: %s", err)
        reply = ICEBREAKER_FALLBACK
    segments = _segments(
        [
            *_by(
                session,
                panel.LEAD,
                [
                    (INTERVIEWER, reply),
                    (INTERVIEWER, INTO_PLAN.get(session.persona or "neutral", "")),
                ],
            ),
            *_handover(session, panel.LEAD, first, first=True),
            *_by(
                session,
                panel.owner(session, first.section),
                [
                    (INTERVIEWER, _entering(session, first, ice)),
                    (_speaker_of(session, first), first.text),
                    *_time_note(session, first),
                ],
            ),
        ]
    )
    _save_answer(session, ice, text, duration_ms, input_mode)
    _ask(first, segments)
    db.session.commit()
    message = " ".join(s["text"] for s in segments)
    return {"action": "next_question", "message": message, "segments": segments}


def _qa_question(session: Session, after: Question, text: str) -> Question:
    qa = Question(
        session_id=session.id,
        section=QA_SECTION,
        order_no=after.order_no + 1000,
        text=text,
        budget_sec=60,
        is_bonus=False,
        is_candidate_qa=True,
    )
    db.session.add(qa)
    return qa


class CandidateQuestionReply(BaseModel):
    has_question: bool
    answer: str = Field(default="", max_length=1200)


def _after_candidate_question(
    session: Session,
    user_id: int,
    asked: list[Question],
    qa: Question,
    text: str,
    duration_ms: int | None,
    input_mode: str,
) -> dict:
    """Answer the candidate's question in role, then "anything else?" or sign off."""
    _save_answer(session, qa, text, duration_ms, input_mode)
    jd = db.session.get(Document, session.jd_id) if session.jd_id else None
    plan = session.plan_json or {}
    history = [
        {"interviewer": q.asked_text, "candidate": a.transcript}
        for q in asked[:-1]
        if q.is_candidate_qa
        and (a := db.session.scalar(db.select(Answer).filter_by(question_id=q.id)))
    ]
    try:
        reply = chat_json(
            user_id,
            render(
                "candidate_question",
                persona=_persona(session, None),
                role=plan.get("role_title") or "the role",
                analysis=plan.get("analysis") or {},
                jd=(jd.raw_text[:MAX_JD_CHARS] if jd else "(not available)"),
                history=history,
                question=qa.asked_text or qa.text,
                answer=text,
            ),
            CandidateQuestionReply,
            max_tokens=400,
            temperature=0.5,
        )
    except (FireError, LimitReached) as err:
        log.warning("Answering the candidate's question failed: %s", err)
        reply = CandidateQuestionReply(has_question=False)

    asked_so_far = sum(1 for q in asked if q.is_candidate_qa)
    # The answer, or a short "No problem at all." when they had no questions.
    answer = reply.answer.strip()
    if reply.has_question and asked_so_far < MAX_CANDIDATE_QUESTIONS:
        segments = _segments(
            _by(
                session,
                panel.LEAD,
                [(INTERVIEWER, answer), (INTERVIEWER, ANYTHING_ELSE)],
            )
        )
        _ask(_qa_question(session, qa, ANYTHING_ELSE), segments)
        db.session.commit()
        message = " ".join(s["text"] for s in segments)
        return {"action": "your_questions", "message": message, "segments": segments}

    segments = _segments(
        _by(
            session,
            panel.LEAD,
            [(INTERVIEWER, answer), (INTERVIEWER, closing(session))],
        )
    )
    session.status = "completed"
    session.ended_at = utcnow()
    db.session.commit()
    message = " ".join(s["text"] for s in segments)
    return {"action": "wrap_up", "message": message, "segments": segments}


class HintOut(BaseModel):
    hint: str = Field(min_length=1, max_length=400)


def hint(session: Session, user_id: int) -> str:
    """One short nudge for the current question (an angle, never the answer)."""
    current = asked_questions(session)[-1]
    if current.is_icebreaker or current.is_candidate_qa:
        raise ValueError("There's no hint for this one; just answer naturally.")
    if current.hint_text:
        return current.hint_text  # one hint per question, no second Fire call
    module = section_info(session, current.section).get("module", modules.DEFAULT)
    out = chat_json(
        user_id,
        render(
            "hint",
            role=(session.plan_json or {}).get("role_title") or "the role",
            difficulty=session.difficulty or "mid",
            question=current.asked_text or current.text,
            module_guidance=modules.guidance(module, "interview"),
            scenario=scenario_of(session, current.section) or "none",
        ),
        HintOut,
        max_tokens=150,
        temperature=0.4,
    )
    current.hint_text = out.hint.strip()
    db.session.commit()
    return current.hint_text


SKIP_ACK = "No problem, let's move on."


def skip(session: Session) -> dict:
    """Move past the current question without an answer (no Fire call)."""
    asked = asked_questions(session)
    current = asked[-1]
    first = db.session.scalar(
        db.select(Question)
        .filter_by(
            session_id=session.id,
            is_bonus=False,
            is_icebreaker=False,
            follow_up_of_id=None,
        )
        .where(Question.is_candidate_qa.is_(False))
        .order_by(Question.order_no)
    )
    if current.is_candidate_qa:
        return _finish(
            session,
            _by(
                session,
                panel.LEAD,
                [(INTERVIEWER, "No problem."), (INTERVIEWER, closing(session))],
            ),
        )
    if current.is_icebreaker:
        nxt = first
        opts = {"next_question": first}
    else:
        opts = options(session, asked, timer_state(session, asked))
        opts.pop("follow_up", None)
        nxt = opts.get("next_question") or opts.get("bonus")
    scenario = scenario_of(session, current.section)
    cur_by = panel.owner(session, current.section)
    parts = [(INTERVIEWER, SKIP_ACK)]
    if scenario is not None and (nxt is None or nxt.section != current.section):
        parts.append((INTERVIEWER, ROLEPLAY_EXIT))
    parts = _by(session, cur_by, parts)
    if nxt is not None:
        parts += _handover(session, cur_by, nxt) + _by(
            session,
            panel.owner(session, nxt.section),
            [
                (INTERVIEWER, _entering(session, nxt, current)),
                (_speaker_of(session, nxt), nxt.text),
                *_time_note(session, nxt),
            ],
        )
        segments = _segments(parts)
        _ask(nxt, segments)
        db.session.commit()
        action = "bonus" if nxt is opts.get("bonus") else "next_question"
        return _reply(action, segments)
    if (
        current_app.config.get("CANDIDATE_QUESTIONS", True)
        and session.mode != "negotiation"
    ):
        segments = _segments(parts + _by(session, panel.LEAD, [(INTERVIEWER, INVITE)]))
        _ask(_qa_question(session, current, INVITE), segments)
        db.session.commit()
        return _reply("your_questions", segments)
    return _finish(
        session, parts + _by(session, panel.LEAD, [(INTERVIEWER, closing(session))])
    )


def _reply(action: str, segments: list[dict]) -> dict:
    return {
        "action": action,
        "message": " ".join(s["text"] for s in segments),
        "segments": segments,
    }


def _finish(session: Session, parts: list[tuple[str, str]]) -> dict:
    segments = _segments(parts)
    session.status = "completed"
    session.ended_at = utcnow()
    db.session.commit()
    return _reply("wrap_up", segments)


def pause(session: Session) -> None:
    if not is_paused(session):
        session.pauses_json = [
            *(session.pauses_json or []),
            [utcnow().isoformat(), None],
        ]
        db.session.commit()


def resume(session: Session) -> None:
    if is_paused(session):
        spans = [list(p) for p in session.pauses_json]
        spans[-1][1] = utcnow().isoformat()
        session.pauses_json = spans
        db.session.commit()


SAME_QUESTION = 0.5
_WORD_RE = re.compile(r"[a-z]+")
_FILLER = frozenset(
    """the a an and or to of in on for with you your about can could would tell me
    more what how did do was were that this it its specific share example thanks
    thank okay got it just please give some any when where which who there those
    these situation instance detail detailing explain clarify elaborate describe
    walk through particular personally""".split()
)


def _stem(word: str) -> str:
    for end in ("ing", "ed", "ly", "es", "s"):
        if word.endswith(end) and len(word) - len(end) >= 4:
            return word[: -len(end)]
    return word


def _time_note(session: Session, question: Question | None) -> list[tuple[str, str]]:
    """Pressure mode: announce the answer time limit with each new main question
    (not in a role-play, where it would break the conversation)."""
    line = (
        pressure.time_line(session.pressure_level) if session.mode == "pressure" else ""
    )
    if not line or question is None or scenario_of(session, question.section):
        return []
    return [(INTERVIEWER, line)]


def _same_question(a: str, b: str) -> bool:
    """Two follow-ups that ask the same thing in different words."""
    wa = {_stem(w) for w in _WORD_RE.findall(a.lower()) if w not in _FILLER}
    wb = {_stem(w) for w in _WORD_RE.findall(b.lower()) if w not in _FILLER}
    if len(wa) < 3 or len(wb) < 3:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= SAME_QUESTION


def _fallback(opts: dict, sign_off: str) -> TurnOut:
    """Used when the model picks a move the clock doesn't allow."""
    for action in ("next_question", "bonus"):
        q = opts.get(action)
        if q is not None:
            return TurnOut(action=action, message=f"Thanks. Let's move on. {q.text}")
    return TurnOut(action="wrap_up", message=sign_off)


def end(session: Session) -> None:
    session.status = "completed"
    session.ended_at = utcnow()
    db.session.commit()
