import base64
import io

import pytest

from app.models import Answer, UsageLimit
from tests.test_sessions import answer, started

CLIP = b"\x1aE\xdf\xa3" + b"\x00" * 4000  # webm magic + padding


def upload(client, auth, session_id, data=CLIP, mime="audio/webm;codecs=opus"):
    return client.post(
        f"/api/sessions/{session_id}/transcribe",
        data={"audio": (io.BytesIO(data), "answer.webm", mime)},
        headers=auth,
        content_type="multipart/form-data",
    )


@pytest.fixture()
def live(client, auth, planned):
    started(client, auth, planned["id"])
    return planned["id"]


def test_transcribes_and_records_spend(client, auth, live, fire):
    fire.transcripts = ["  I   led the billing API.  "]
    res = upload(client, auth, live)
    assert res.status_code == 200
    assert res.get_json() == {"text": "I led the billing API."}
    sent = fire.audio[0]
    assert sent.startswith("data:audio/webm;base64,")
    assert base64.b64decode(sent.split(",", 1)[1]) == CLIP
    row = UsageLimit.query.one()
    assert row.fire_spend_usd == pytest.approx(0.0033)  # 3 planning calls + 1 clip
    assert Answer.query.count() == 0  # text is saved only when the turn is sent


def test_voice_turn_is_marked(client, auth, live):
    text = upload(client, auth, live).get_json()["text"]
    res = client.post(
        f"/api/sessions/{live}/turns",
        json={"text": text, "duration_ms": 300_500, "input_mode": "voice"},
        headers=auth,
    )
    assert res.status_code == 200
    assert res.get_json()["session"]["transcript"][0]["input_mode"] == "voice"
    assert Answer.query.one().input_mode == "voice"


def test_typed_turns_default_to_text(client, auth, live):
    answer(client, auth, live)
    assert Answer.query.one().input_mode == "text"


def test_silence_is_rejected_without_saving(client, auth, live, fire):
    fire.transcripts = ["   "]
    res = upload(client, auth, live)
    assert res.status_code == 422 and "didn't catch" in res.get_json()["error"]


def test_rejects_bad_clips(app, client, auth, live, fire):
    assert upload(client, auth, live, data=b"tiny").status_code == 422
    assert upload(client, auth, live, mime="video/mp4").status_code == 400
    app.config["MAX_AUDIO_BYTES"] = 2000
    assert upload(client, auth, live).status_code == 413
    no_file = client.post(f"/api/sessions/{live}/transcribe", headers=auth)
    assert no_file.status_code == 400
    assert fire.audio == []


def test_needs_an_active_session(client, auth, planned):
    assert upload(client, auth, planned["id"]).status_code == 409
