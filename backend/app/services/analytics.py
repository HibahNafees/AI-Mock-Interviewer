"""Delivery analytics computed from transcripts and browser timings (no Fire calls).

Pace needs a spoken answer: a typed answer's duration is time spent typing.
Whisper keeps "um"/"uh", so filler counts are meaningful for spoken answers only.
"""

import re
from dataclasses import dataclass

WORD_RE = re.compile(r"[A-Za-z0-9']+")
FILLERS = {
    "um": re.compile(r"\b(?:um+|umm+)\b", re.I),
    "uh": re.compile(r"\b(?:uh+|uhh+)\b", re.I),
    "er": re.compile(r"\b(?:er|erm)\b", re.I),
    "ah": re.compile(r"\bah+\b", re.I),
    "you know": re.compile(
        r"\byou know\b(?!\s+(?:what|how|why|when|where|that|if))", re.I
    ),
}
MIN_PACE_SEC = 10  # shorter clips give a noisy words-per-minute figure
SLOW_WPM, FAST_WPM = 110, 170
FILLERS_PER_MIN_HIGH = 4.0
LONG_RATIO, SHORT_RATIO = 1.5, 0.35


@dataclass
class Clip:
    """One answer: its transcript, browser-measured duration and how it was given."""

    text: str
    duration_ms: int | None
    input_mode: str


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def filler_counts(text: str) -> dict[str, int]:
    counts = {name: len(rx.findall(text)) for name, rx in FILLERS.items()}
    return {k: v for k, v in counts.items() if v}


def delivery(clips: list[Clip], budget_sec: int | None) -> dict:
    """Analytics for one question (its main answer plus any follow-up answers)."""
    words = sum(word_count(c.text) for c in clips)
    seconds = sum((c.duration_ms or 0) for c in clips) / 1000
    spoken = [c for c in clips if c.input_mode == "voice" and c.duration_ms]
    spoken_sec = sum(c.duration_ms for c in spoken) / 1000
    spoken_words = sum(word_count(c.text) for c in spoken)
    fillers: dict[str, int] = {}
    for c in spoken:
        for k, v in filler_counts(c.text).items():
            fillers[k] = fillers.get(k, 0) + v

    wpm = round(spoken_words / spoken_sec * 60) if spoken_sec >= MIN_PACE_SEC else None
    filler_total = sum(fillers.values())
    fillers_per_min = (
        round(filler_total / spoken_sec * 60, 1) if spoken_sec >= MIN_PACE_SEC else None
    )
    data = {
        "words": words,
        "duration_sec": round(seconds),
        "budget_sec": budget_sec,
        "spoken": bool(spoken),
        "wpm": wpm,
        "fillers": fillers,
        "filler_total": filler_total,
        "fillers_per_min": fillers_per_min,
    }
    data["tips"] = delivery_tips(data)
    return data


def delivery_tips(d: dict) -> list[str]:
    tips = []
    wpm, budget, secs = d["wpm"], d["budget_sec"], d["duration_sec"]
    if wpm is not None and wpm > FAST_WPM:
        tips.append(
            f"You spoke at about {wpm} words per minute; slow down a little "
            f"(around {SLOW_WPM}–{FAST_WPM - 20} is easy to follow)."
        )
    elif wpm is not None and wpm < SLOW_WPM:
        tips.append(
            f"You spoke at about {wpm} words per minute; a slightly brisker pace "
            "will sound more confident."
        )
    if d["fillers_per_min"] is not None and d["fillers_per_min"] > FILLERS_PER_MIN_HIGH:
        top = max(d["fillers"], key=d["fillers"].get)
        tips.append(
            f'About {d["fillers_per_min"]:g} filler words a minute (mostly "{top}"); '
            "a short silent pause works better than a filler."
        )
    if budget and budget >= 60 and secs > budget * LONG_RATIO:
        tips.append(
            f"This took about {_mins(secs)} against a {_mins(budget)} budget; "
            "lead with the headline and cut background detail."
        )
    elif budget and budget >= 120 and 0 < secs < budget * SHORT_RATIO:
        tips.append(
            f"This was short ({_mins(secs)} of a {_mins(budget)} budget); "
            "add a concrete example and the result."
        )
    return tips


def _mins(sec: float) -> str:
    if sec < 90:
        return f"{round(sec)} s"
    return f"{sec / 60:.1f} min"


def session_summary(per_question: list[dict]) -> dict:
    """Totals across the session's questions for the report header."""
    spoken = [d for d in per_question if d["wpm"] is not None]
    fillers: dict[str, int] = {}
    for d in per_question:
        for k, v in d["fillers"].items():
            fillers[k] = fillers.get(k, 0) + v
    return {
        "questions": len(per_question),
        "answer_sec": sum(d["duration_sec"] for d in per_question),
        "budget_sec": sum(d["budget_sec"] or 0 for d in per_question),
        "avg_wpm": (
            round(sum(d["wpm"] for d in spoken) / len(spoken)) if spoken else None
        ),
        "fillers": fillers,
        "filler_total": sum(fillers.values()),
        "over_budget": sum(
            1
            for d in per_question
            if d["budget_sec"]
            and d["budget_sec"] >= 60
            and d["duration_sec"] > d["budget_sec"] * LONG_RATIO
        ),
    }
