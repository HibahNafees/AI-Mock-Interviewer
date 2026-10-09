"""A stand-in for the Fire client. Tests never call the real API."""

import json

from app.services.fire import ChatResult, FireResult

ANALYSIS = {
    "role_title": "Backend Engineer",
    "field": "software engineering",
    "seniority": "mid",
    "competencies": [
        {"name": "API design", "description": "Designs clean HTTP APIs"},
        {"name": "Databases", "description": "Models and tunes SQL data"},
    ],
    "formats": ["behavioral", "resume_deepdive", "technical", "coding"],
    "licensed_field": False,
}

PLAN = {
    "sections": [
        {
            "name": "Background",
            "module": "resume_deepdive",
            "minutes": 3,
            "questions": ["Walk me through your Acme project."],
        },
        {
            "name": "Technical",
            "module": "technical",
            "minutes": 5,
            "questions": [
                "How would you design a rate limiter?",
                "How do you index a slow query?",
            ],
        },
    ],
    "reserve": [
        {"section": "Technical", "text": "What is your favorite database and why?"}
    ],
}

RUBRIC = {
    "criteria": [
        {"name": "API design", "kind": "role", "weight": 0.4, "description": "d"},
        {"name": "Structure", "kind": "universal", "weight": 0.2, "description": "d"},
        {"name": "Clarity", "kind": "universal", "weight": 0.2, "description": "d"},
        {"name": "Relevance", "kind": "universal", "weight": 0.2, "description": "d"},
    ]
}


SCORE = {
    "criteria": [
        {"name": "API design", "score": 4, "comment": "Clear ownership of the API."},
        {"name": "Structure", "score": 3, "comment": "Wandered a little."},
        {"name": "clarity", "score": 4, "comment": "Easy to follow."},
        {"name": "Relevance", "score": 2, "comment": "Drifted off topic."},
        {"name": "Not in the rubric", "score": None, "comment": ""},
    ],
    "summary": "Good ownership; the result was missing.",
    "weak_moments": [
        {"quote": "My answer", "why": "Too vague."},
        {"quote": "something the candidate never said", "why": "Invented."},
        {"quote": "My answer", "why": "The transcription error sounds unprofessional."},
    ],
    "missing_points": [
        {"point": "A measurable result", "covered": False},
        {"point": "Their own role", "covered": True},
    ],
    "star": {
        "situation": True,
        "task": True,
        "action": True,
        "result": False,
        "note": "No result given.",
    },
    "stronger_version": [
        {
            "text": "At Acme I built the billing API.",
            "source": "Built the Acme billing API",
        },
        {"text": "That led to [add the result you achieved].", "source": None},
    ],
    "changes": [{"kind": "added", "text": "A result", "reason": "Shows impact."}],
    "tips": ["Name the scale you worked at."],
}

REPAIR = {
    "stronger_version": [
        {
            "text": "I built the Acme billing API.",
            "source": "Built the Acme billing API",
        },
        {"text": "The result was [add the result you achieved].", "source": None},
    ]
}

SUMMARY = {
    "reasoning": "Solid ownership, but results were missing.",
    "takeaways": ["Quantify results.", "Lead with the point.", "Keep answers tight."],
}


class FakeFire:
    """Answers by prompt type; interviewer turns come from `turns` (else next_question)."""

    price = 0.001

    def __init__(self):
        self.calls: list[dict] = []
        self.turns: list[dict | str] = []
        # Queued scorer replies; an Exception instance is raised instead.
        self.scores: list[dict | str | Exception] = []
        # Queued rewrite-repair replies (default: one grounded sentence).
        self.repairs: list[dict | str] = []
        # What the JD analysis and plan prompts return (override per test).
        self.analysis: dict = ANALYSIS
        self.plan: dict | str = PLAN
        self.transcripts: list[str] = []
        self.audio: list[str] = []
        # Speech calls as (text, voice); set speech_error to make them fail.
        self.spoken: list[tuple[str, str | None]] = []
        self.speech_error: Exception | None = None
        self.small_talk_error: Exception | None = None

    def chat(
        self, messages, system_prompt=None, max_tokens=1024, temperature=0.4, model=None
    ):
        prompt = messages[0]["content"]
        self.calls.append(
            {
                "prompt": prompt,
                "messages": messages,
                "model": model,
                "temperature": temperature,
            }
        )
        if "Analyze this job description" in prompt:
            body = self.analysis
        elif "question plan" in prompt:
            body = self.plan
        elif "scoring rubric" in prompt:
            body = RUBRIC
        elif "Score one question" in prompt:
            body = self.scores.pop(0) if self.scores else SCORE
            if isinstance(body, Exception):
                raise body
        elif "summary for a mock-interview" in prompt:
            body = SUMMARY
        elif 'Fix a "stronger version"' in prompt:
            body = self.repairs.pop(0) if self.repairs else REPAIR
        elif "moment of small talk" in prompt:
            if self.small_talk_error:
                raise self.small_talk_error
            body = {"message": "Doing well, thanks for asking!"}
        elif self.turns:
            body = self.turns.pop(0)
        else:
            body = {"action": "next_question", "message": "Thanks. Next question."}
        content = body if isinstance(body, str) else json.dumps(body)
        return ChatResult(content=content, price_usd=self.price)

    def transcribe(self, audio_data_url):
        self.audio.append(audio_data_url)
        text = self.transcripts.pop(0) if self.transcripts else "I led the billing API."
        return FireResult(data={"text": text}, price_usd=0.0003)

    def speech(self, text, voice=None):
        if self.speech_error:
            raise self.speech_error
        self.spoken.append((text, voice))
        return FireResult(data={"audio": "QUJD", "format": "mp3"}, price_usd=0.0002)

    def kinds(self) -> list[str]:
        out = []
        for c in self.calls:
            p = c["prompt"]
            for marker, kind in (
                ("Analyze this job description", "analysis"),
                ("question plan", "plan"),
                ("scoring rubric", "rubric"),
                ("Score one question", "score"),
                ("summary for a mock-interview", "summary"),
                ('Fix a "stronger version"', "repair"),
            ):
                if marker in p:
                    out.append(kind)
                    break
            else:
                out.append("turn")
        return out
