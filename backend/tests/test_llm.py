import pytest
from pydantic import BaseModel

from app.models import UsageLimit
from app.services.fire import FireError
from app.services.llm import chat_json, render


class Out(BaseModel):
    answer: int


def test_render_keeps_json_braces():
    text = render("rubric", role={"field": "x"}, difficulty="mid")
    assert '{"field": "x"}' in text and '"criteria"' in text


def test_parses_fenced_json_and_records_spend(app, signup, fire):
    signup()
    fire.turns = ['```json\n{"answer": 42}\n```']
    assert chat_json(1, "q", Out).answer == 42
    row = UsageLimit.query.one()
    assert row.llm_calls == 1 and row.fire_spend_usd == pytest.approx(0.001)
    assert fire.calls[0]["model"] == "gpt-4o-mini"


def test_retries_once_on_invalid_json(app, signup, fire):
    signup()
    fire.turns = ["not json", '{"answer": 7}']
    assert chat_json(1, "q", Out).answer == 7
    retry = fire.calls[1]["messages"]
    assert retry[1]["content"] == "not json" and "valid JSON" in retry[2]["content"]


def test_gives_up_after_two_invalid(app, signup, fire):
    signup()
    fire.turns = ["nope", '{"answer": "x"}']
    with pytest.raises(FireError):
        chat_json(1, "q", Out)
    assert UsageLimit.query.one().llm_calls == 2
