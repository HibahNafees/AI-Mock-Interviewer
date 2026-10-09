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


class FakeFire:
    """Answers by prompt type; interviewer turns come from `turns` (else next_question)."""

    price = 0.001

    def __init__(self):
        self.calls: list[dict] = []
        self.turns: list[dict | str] = []
        self.transcripts: list[str] = []
        self.audio: list[str] = []

    def chat(
        self, messages, system_prompt=None, max_tokens=1024, temperature=0.4, model=None
    ):
        prompt = messages[0]["content"]
        self.calls.append({"prompt": prompt, "messages": messages, "model": model})
        if "Analyze this job description" in prompt:
            body = ANALYSIS
        elif "question plan" in prompt:
            body = PLAN
        elif "scoring rubric" in prompt:
            body = RUBRIC
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

    def kinds(self) -> list[str]:
        out = []
        for c in self.calls:
            p = c["prompt"]
            out.append(
                "analysis"
                if "Analyze this job description" in p
                else (
                    "plan"
                    if "question plan" in p
                    else "rubric" if "scoring rubric" in p else "turn"
                )
            )
        return out
