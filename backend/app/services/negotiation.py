"""Negotiation role-play: a recruiter makes a low offer and the candidate negotiates.

The plan and rubric are fixed templates (no Fire call to build them); the recruiter
is an ordinary role-play character with private instructions on how far it may
move. Scored on anchoring, justification and staying calm.
"""

from pydantic import BaseModel, Field, field_validator

from ..models import Session
from .planning import Criterion, PlanOut, PlanSectionOut, RubricOut, Scenario

SECTION = "Offer negotiation"
RECRUITER = "Sam"
MIN_MINUTES, MAX_MINUTES = 5, 20
# A negotiation is one long conversation: more replies than a normal role-play.
MAX_TURNS = 12

FIRMNESS = {
    "friendly": "You are warm and reasonably flexible once the ask is well justified.",
    "neutral": "You are businesslike: you move only for solid reasons.",
    "tough": 'You are firm and push back hard ("this is already at the top of our band"), '
    "but always polite and respectful.",
}

PRIVATE = (
    "You are the recruiter. Your first offer is deliberately on the low side. You have "
    "approval to improve it, but only partway, and only when the candidate names a "
    "specific number or range and backs it up (their experience, results, skills, "
    "market rates or a competing offer). Move in small steps: a modest raise to the "
    "base, a signing bonus, extra leave, a remote day or an earlier salary review. "
    "Never move for vague asks, demands or ultimatums; hold firm and ask what they "
    "had in mind. Don't reveal how far you can go. If they accept too quickly, "
    "accept happily. Once you've agreed on terms, confirm them and say you'll send "
    "the paperwork. {firmness}"
)


class NegotiationIn(BaseModel):
    offer: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)
    company: str = Field(default="", max_length=120)

    @field_validator("offer", "target", "company")
    @classmethod
    def strip(cls, v: str) -> str:
        return " ".join(v.split())


def plan(
    terms: NegotiationIn, role: str, user_name: str, persona: str, minutes: int
) -> PlanOut:
    first = (user_name.split(" ")[0] if user_name else "") or "there"
    at = f" at {terms.company}" if terms.company else ""
    scenario = Scenario(
        character=f"{RECRUITER}, the recruiter{at} calling with your offer",
        setting=f"A phone call after your final interview for the {role} role. "
        f"The offer is {terms.offer}.",
        goal=f"negotiate a better offer than {terms.offer} while keeping the "
        "relationship positive",
        private=PRIVATE.format(firmness=FIRMNESS.get(persona, FIRMNESS["neutral"])),
    )
    opening = (
        f"Hi {first}, it's {RECRUITER}{at}. I've got good news: we'd love to offer you "
        f"the {role} position, at {terms.offer}. How does that sound?"
    )
    return PlanOut(
        sections=[
            PlanSectionOut(
                name=SECTION,
                module="roleplay",
                minutes=minutes,
                questions=[opening],
                scenario=scenario,
            )
        ],
        reserve=[],
    )


RUBRIC = RubricOut(
    criteria=[
        Criterion(
            name="Anchoring",
            kind="role",
            weight=0.3,
            description="Names a specific, ambitious but defensible number or range "
            "and holds it, instead of accepting the first offer or asking vaguely.",
            strong_answer="Thanks the recruiter, then asks for a specific figure above "
            "the offer and doesn't drop it at the first pushback.",
        ),
        Criterion(
            name="Justification",
            kind="role",
            weight=0.3,
            description="Backs the ask with concrete value: experience, results and "
            "skills from their background, market rates, or competing factors.",
            strong_answer="Links the number to two or three specific things they "
            "bring, not to personal needs.",
        ),
        Criterion(
            name="Composure",
            kind="role",
            weight=0.25,
            description="Stays calm, polite and confident under pushback or \"that's "
            'our best": neither caves at once nor turns defensive or aggressive.',
            strong_answer="Acknowledges the constraint, explores other levers (bonus, "
            "leave, review date) and keeps a warm tone.",
        ),
        Criterion(
            name="Clarity",
            kind="universal",
            weight=0.15,
            description="Says what they want clearly and confirms the agreed terms.",
            strong_answer="Ends by summarizing exactly what was agreed.",
        ),
    ]
)


# Shown (and summarized) instead of hire / lean hire / no hire.
VERDICTS = {
    "hire": "strong negotiation",
    "lean hire": "solid, with room to push",
    "no hire": "needs more practice",
}


def info(session: Session) -> dict | None:
    if session.mode != "negotiation":
        return None
    return (session.plan_json or {}).get("negotiation")


def intro(session: Session) -> str:
    return f"This is a {session.duration_min}-minute offer negotiation practice."
