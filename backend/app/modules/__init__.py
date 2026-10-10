"""Interview format modules: reusable interviewer behaviors mixed per job.

Each module's guidance lives in prompts/modules/<name>.txt with [plan], [interview]
and [score] blocks, used by the plan, interviewer-turn and scoring prompts. A new
field needs a new mix of modules (chosen by the JD analysis), not new code.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

GUIDANCE_DIR = Path(__file__).resolve().parent.parent / "prompts" / "modules"
BLOCK_RE = re.compile(r"^\[(plan|interview|score)\]\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Module:
    name: str
    label: str
    blurb: str


MODULES: dict[str, Module] = {
    m.name: m
    for m in (
        Module("behavioral", "Behavioral", "“Tell me about a time…” stories (STAR)"),
        Module("resume_deepdive", "Résumé deep-dive", "Probes your résumé lines"),
        Module("technical", "Technical Q&A", "Knowledge questions for the field"),
        Module("case", "Case", "Business problems, sizing and metrics"),
        Module("scenario", "Scenario", "“What would you do if…” judgment calls"),
        Module("portfolio", "Portfolio walkthrough", "Walk through your past work"),
        Module("roleplay", "Role-play", "The interviewer plays a character"),
        Module(
            "coding", "Coding", "Solve a problem in a code editor and talk it through"
        ),
        Module(
            "system_design",
            "System design",
            "Sketch a system on a whiteboard and explain it",
        ),
    )
}
DEFAULT = "behavioral"


def known(name: str) -> bool:
    return name in MODULES


@cache
def _blocks(name: str) -> dict[str, str]:
    text = (GUIDANCE_DIR / f"{name}.txt").read_text()
    parts = BLOCK_RE.split(text)
    # ["", "plan", "...", "interview", "...", "score", "..."]
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def guidance(name: str, stage: str) -> str:
    """The module's guidance for `stage` ("plan", "interview" or "score")."""
    return _blocks(name if known(name) else DEFAULT).get(stage, "")


def plan_guidance(names: list[str]) -> str:
    return "\n".join(f"- {n}: {guidance(n, 'plan')}" for n in names if known(n))
