"""Job description decoder: an interpretation of what a posting really asks for.

One Fire call per distinct JD (cached by text hash; the JD text isn't stored).
Every flag must quote the posting; quotes that aren't in it are dropped.
"""

import hashlib
import re
import secrets
from collections import Counter

from flask import current_app
from pydantic import BaseModel, Field

from ..extensions import db
from ..models import JdDecode
from . import limits
from .llm import chat_json, render

MAX_JD_CHARS = 8000
MIN_JD_CHARS = 200
WORD_RE = re.compile(r"[a-z][a-z\-]{3,}")
# Words every posting uses; repeats of these say nothing.
COMMON = frozenset(
    """with that this will have from your about their they them what when which
    work working works team role roles experience experienced years year ability
    able skills skill strong knowledge including include includes such also other
    more must should would could into across within using used based well good
    company candidate candidates position job jobs looking join plus preferred
    required requirements responsibilities qualifications opportunity apply etc
    help helping make makes like within new our we you are the and for""".split()
)
SIGNAL_MIN = 3
MAX_SIGNALS = 6


class Evidence(BaseModel):
    point: str = Field(min_length=1, max_length=300)
    evidence: str | None = Field(default=None, max_length=400)


class Guess(BaseModel):
    guess: str = Field(min_length=1, max_length=120)
    why: str = Field(default="", max_length=300)
    evidence: str | None = Field(default=None, max_length=400)


class LikelyQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    why: str = Field(default="", max_length=300)


class Competency(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    why: str = Field(default="", max_length=300)


class DecodeOut(BaseModel):
    role_title: str = Field(default="", max_length=160)
    summary: str = Field(min_length=1, max_length=800)
    team_size: Guess | None = None
    pace: Guess | None = None
    priorities: list[Evidence] = Field(default_factory=list, max_length=6)
    green_flags: list[Evidence] = Field(default_factory=list, max_length=5)
    red_flags: list[Evidence] = Field(default_factory=list, max_length=5)
    likely_questions: list[LikelyQuestion] = Field(default_factory=list, max_length=10)
    competencies: list[Competency] = Field(default_factory=list, max_length=8)


class DecodeError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%$+#]+", " ", text.lower()).split())


def text_hash(jd: str) -> str:
    return hashlib.sha256(_norm(jd).encode()).hexdigest()


def ip_hash(ip: str | None) -> str | None:
    if not ip:
        return None
    salt = current_app.config.get("SECRET_KEY") or ""
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


def signals(jd: str) -> list[dict]:
    """Repeated meaningful words, counted exactly ('stakeholders' ×6)."""
    words = [w.strip("-") for w in WORD_RE.findall(jd.lower())]
    stems: Counter = Counter()
    shown: dict[str, Counter] = {}
    for w in words:
        if w in COMMON:
            continue
        stem = w[:-1] if w.endswith("s") and len(w) > 4 else w
        stems[stem] += 1
        shown.setdefault(stem, Counter())[w] += 1
    return [
        {"word": shown[s].most_common(1)[0][0], "count": n}
        for s, n in stems.most_common(MAX_SIGNALS)
        if n >= SIGNAL_MIN
    ]


def _quoted(evidence: str | None, jd_norm: str) -> str | None:
    if not evidence:
        return None
    q = _norm(evidence)
    return evidence.strip() if q and len(q.split()) >= 2 and q in jd_norm else None


def _clean(out: DecodeOut, jd: str) -> dict:
    """Keep only flags and priorities whose quote is really in the posting."""
    jd_norm = _norm(jd)

    def items(rows: list[Evidence]) -> list[dict]:
        kept = []
        for r in rows:
            quote = _quoted(r.evidence, jd_norm)
            if quote:
                kept.append({"point": r.point.strip(), "evidence": quote})
        return kept

    def guess(g: Guess | None) -> dict | None:
        if g is None:
            return None
        return {
            "guess": g.guess.strip(),
            "why": g.why.strip(),
            "evidence": _quoted(g.evidence, jd_norm),
        }

    return {
        "role_title": out.role_title.strip(),
        "summary": out.summary.strip(),
        "team_size": guess(out.team_size),
        "pace": guess(out.pace),
        "priorities": items(out.priorities)[:5],
        "green_flags": items(out.green_flags)[:4],
        "red_flags": items(out.red_flags)[:4],
        "likely_questions": [q.model_dump() for q in out.likely_questions][:8],
        "competencies": [c.model_dump() for c in out.competencies][:6],
        "signals": signals(jd),
    }


def decode(jd: str, user_id: int | None, ip: str | None) -> JdDecode:
    jd = (jd or "").strip()
    if len(jd) < MIN_JD_CHARS:
        raise DecodeError("Paste the full job description (at least a few sentences).")
    jd = jd[:MAX_JD_CHARS]
    key = text_hash(jd)
    cached = db.session.scalar(db.select(JdDecode).filter_by(text_hash=key))
    if cached is not None:
        return cached  # same posting decoded before: no Fire call, no cap used
    visitor = ip_hash(ip)
    limits.check_can_decode(user_id, visitor)
    out = chat_json(
        user_id,
        render("jd_decode", jd=jd, signals=signals(jd)),
        DecodeOut,
        max_tokens=1800,
        temperature=0.3,
    )
    row = JdDecode(
        text_hash=key,
        share_token=secrets.token_urlsafe(16)[:22],
        result_json=_clean(out, jd),
        user_id=user_id,
        ip_hash=None if user_id else visitor,
    )
    db.session.add(row)
    limits.record_decode(user_id)
    db.session.commit()
    return row


def decode_dict(row: JdDecode) -> dict:
    return {"share_token": row.share_token, **row.result_json}
