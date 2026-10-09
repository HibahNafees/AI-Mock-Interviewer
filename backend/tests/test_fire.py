import pytest
import requests

from app.services.fire import FireClient, FireError


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}
        self.text = str(body)

    def json(self):
        return self._body


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, json, headers, timeout):
        self.requests.append({"url": url, "json": json, "headers": headers})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


OK = FakeResponse(200, {"content": "hi", "meta": {"price": {"usd": 0.0002}}})


def client(*responses):
    c = FireClient("fire_sk_test", "https://fire.example/")
    c.http = FakeHttp(*responses)
    return c


def test_chat_sends_key_and_returns_price():
    c = client(OK)
    out = c.chat(
        [{"role": "user", "content": "x"}], system_prompt="s", model="gpt-4o-mini"
    )
    assert out.content == "hi" and out.price_usd == 0.0002
    req = c.http.requests[0]
    assert req["url"] == "https://fire.example/v1/chat"
    assert req["headers"]["Authorization"] == "Bearer fire_sk_test"
    assert req["json"]["species_name"] == "gpt-4o-mini"
    assert req["json"]["system_prompt"] == "s"


def test_retries_once_on_5xx():
    c = client(FakeResponse(502), OK)
    assert c.chat([{"role": "user", "content": "x"}]).content == "hi"
    assert len(c.http.requests) == 2


def test_gives_up_after_second_failure():
    c = client(FakeResponse(500), requests.Timeout())
    with pytest.raises(FireError) as err:
        c.chat([{"role": "user", "content": "x"}])
    assert err.value.status == 504


def test_does_not_retry_4xx_and_hides_key():
    c = client(FakeResponse(401, {"error": "bad key"}))
    with pytest.raises(FireError) as err:
        c.chat([{"role": "user", "content": "x"}])
    assert len(c.http.requests) == 1
    assert err.value.status == 503
    assert "fire_sk" not in err.value.message


def test_missing_key():
    c = FireClient(None, "https://fire.example")
    with pytest.raises(FireError):
        c.chat([{"role": "user", "content": "x"}])
