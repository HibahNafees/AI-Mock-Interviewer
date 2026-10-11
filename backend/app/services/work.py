"""Work the candidate shows alongside an answer: code from the editor (coding
round) or a whiteboard sketch described as text (system design).

It is saved with the answer and reaches the interviewer and the scorer as part
of what the candidate said; pace and filler analytics use the spoken words only.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_CHARS = 20_000
# Output of the candidate's last in-browser run (Python or JavaScript).
MAX_OUTPUT_CHARS = 4_000
# What the interviewer prompt keeps of earlier work (the latest is sent in full).
HISTORY_CHARS = 2_000
LANGUAGES = (
    "python",
    "javascript",
    "typescript",
    "java",
    "csharp",
    "cpp",
    "go",
    "ruby",
    "kotlin",
    "swift",
    "sql",
    "plaintext",
)


class WorkIn(BaseModel):
    kind: Literal["code", "whiteboard"]
    language: str = Field(default="plaintext", max_length=20)
    content: str = Field(min_length=1, max_length=MAX_CHARS)
    output: str | None = Field(default=None, max_length=MAX_OUTPUT_CHARS)

    @field_validator("language")
    @classmethod
    def known_language(cls, v: str) -> str:
        return v if v in LANGUAGES else "plaintext"

    @field_validator("content")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("The editor is empty")
        return v.rstrip()


def as_text(work: dict | None) -> str:
    """The work as the interviewer and scorer read it, or ""."""
    if not work:
        return ""
    if work.get("kind") == "code":
        text = f"[Code in the editor ({work.get('language') or 'plaintext'})]\n{work['content']}"
        if work.get("output"):
            text += f"\n[Output when the candidate last ran it]\n{work['output']}"
        return text
    return f"[Whiteboard sketch, described as text]\n{work['content']}"


def with_work(transcript: str, work: dict | None) -> str:
    """What the candidate said, followed by any code or sketch they showed."""
    extra = as_text(work)
    return f"{transcript}\n\n{extra}" if extra else transcript
