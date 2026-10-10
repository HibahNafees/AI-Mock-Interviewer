"""Panel interview: two or three interviewers take turns, one per plan section.

Each section belongs to a panelist chosen from its module (the peer asks the
technical parts, HR the behavioral ones, the hiring manager the rest). Their lines
carry a "panelist" key so the browser can label them and give each a voice.
"""

from ..models import Session

LEAD = "hm"
PANELISTS = {
    "hm": {"name": "Priya", "title": "the hiring manager"},
    "peer": {"name": "Marcus", "title": "a senior colleague on the team"},
    "hr": {"name": "Elena", "title": "from the People team"},
}
OWNER = {
    "technical": "peer",
    "coding": "peer",
    "system_design": "peer",
    "case": "peer",
    "portfolio": "peer",
    "behavioral": "hr",
}
# Short interviews get a panel of two.
SMALL_PANEL_MAX_MIN = 10


def members(duration_min: int) -> list[str]:
    if duration_min <= SMALL_PANEL_MAX_MIN:
        return ["hm", "peer"]
    return ["hm", "peer", "hr"]


def assign(session: Session) -> None:
    """Give each plan section to a panelist (call after the plan changes)."""
    plan = dict(session.plan_json or {})
    keys = members(session.duration_min)
    sections = []
    for s in plan.get("sections", []):
        owner = OWNER.get(s.get("module"), LEAD)
        sections.append({**s, "panelist": owner if owner in keys else LEAD})
    plan["sections"] = sections
    plan["panel"] = [{"key": k, **PANELISTS[k]} for k in keys]
    session.plan_json = plan


def owner(session: Session, section: str | None) -> str | None:
    """The panelist who asks in `section` (None outside a panel interview)."""
    if session.mode != "panel":
        return None
    for s in (session.plan_json or {}).get("sections", []):
        if s["name"] == section:
            return s.get("panelist") or LEAD
    return LEAD


def name(key: str) -> str:
    return PANELISTS[key]["name"]


def introductions(session: Session) -> str:
    """ "I'm Priya, the hiring manager, and with me are Marcus, … and Elena, …" """
    keys = [p["key"] for p in (session.plan_json or {}).get("panel", [])] or [LEAD]
    others = [f"{name(k)}, {PANELISTS[k]['title']}" for k in keys if k != LEAD]
    me = f"I'm {name(LEAD)}, {PANELISTS[LEAD]['title']}"
    if not others:
        return f"{me}."
    joined = others[0] if len(others) == 1 else f"{others[0]}, and {others[1]}"
    return f"{me}, and with me {'is' if len(others) == 1 else 'are'} {joined}. We'll take turns asking questions."


def persona_note(key: str, session: Session) -> str:
    """Added to the interviewer prompt: who is speaking on the panel."""
    size = len((session.plan_json or {}).get("panel", [])) or 1
    p = PANELISTS[key]
    return (
        f"You are {p['name']}, {p['title']}, one of {size} interviewers on a panel; "
        "this part of the interview is yours, so speak as yourself in first person."
    )


def handover(to_key: str, first: bool = False) -> tuple[str, str]:
    """What the outgoing panelist says, and how the next one opens."""
    p = PANELISTS[to_key]
    if first:  # right after the introductions
        return f"{p['name']} will start us off.", ""
    return (
        f"Thanks. I'll hand over to {p['name']} now.",
        f"Hi, {p['name']} here, {p['title']}.",
    )


def info(session: Session) -> list[dict] | None:
    if session.mode != "panel":
        return None
    return (session.plan_json or {}).get("panel")
