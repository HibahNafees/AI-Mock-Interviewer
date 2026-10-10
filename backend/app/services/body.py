"""Body language feedback (opt-in): percentages measured in the browser by
MediaPipe, one set per answer. No video or image ever reaches the server, and
none of this goes to Fire or affects the scores.
"""

from pydantic import BaseModel, Field

# Below these, the report suggests working on it.
EYE_CONTACT_OK = 60
UPRIGHT_OK = 70
FIDGET_OK = 25
MIN_SAMPLES = 8  # about 2 seconds of camera at 4 frames a second


class BodyIn(BaseModel):
    samples: int = Field(ge=0, le=10_000)
    face_pct: int | None = Field(default=None, ge=0, le=100)
    eye_contact_pct: int | None = Field(default=None, ge=0, le=100)
    upright_pct: int | None = Field(default=None, ge=0, le=100)
    fidget_pct: int | None = Field(default=None, ge=0, le=100)


def _avg(values: list[tuple[int, int]]) -> int | None:
    """Sample-weighted average of (pct, samples)."""
    total = sum(n for _, n in values)
    return round(sum(p * n for p, n in values) / total) if total else None


def summary(rows: list[dict | None]) -> dict | None:
    """The interview's body language from each answer's numbers, with tips."""
    rows = [r for r in rows if r and r.get("samples", 0) >= MIN_SAMPLES]
    if not rows:
        return None
    out = {
        k: _avg([(r[k], r["samples"]) for r in rows if r.get(k) is not None])
        for k in ("eye_contact_pct", "upright_pct", "fidget_pct", "face_pct")
    }
    tips = []
    if out["face_pct"] is not None and out["face_pct"] < 70:
        tips.append(
            "Your face was often out of view: centre the camera at eye level before you start."
        )
    if out["eye_contact_pct"] is not None and out["eye_contact_pct"] < EYE_CONTACT_OK:
        tips.append(
            "Look at the camera (not the screen) when you make your key points; "
            "glancing away to think is fine."
        )
    if out["upright_pct"] is not None and out["upright_pct"] < UPRIGHT_OK:
        tips.append(
            "Sit up with both shoulders level; it reads as confident and helps your voice."
        )
    if out["fidget_pct"] is not None and out["fidget_pct"] > FIDGET_OK:
        tips.append(
            "Your hands and head moved a lot: rest your hands, and save gestures for emphasis."
        )
    return {**out, "answers": len(rows), "tips": tips}
