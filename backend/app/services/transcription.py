"""Answer clip → text via Fire transcribe. Audio is never stored.

The clip exists only in memory for the length of the request: it is base64-encoded
into the Fire call and then dropped. Only the returned text is kept (as an Answer).
"""

import base64

from .fire import get_fire
from .limits import record_fire_call

# What browsers' MediaRecorder produces (Chrome/Firefox: webm or ogg; Safari: mp4).
AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav")


class TranscriptionError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def base_type(mime: str | None) -> str:
    return (mime or "").split(";")[0].strip().lower()


def transcribe(user_id: int, audio: bytes, mime: str | None) -> str:
    kind = base_type(mime)
    if kind not in AUDIO_TYPES:
        raise TranscriptionError(
            "Unsupported audio format; try another browser or type"
        )
    if len(audio) < 1000:
        raise TranscriptionError("That recording was empty; please try again", 422)

    data_url = f"data:{kind};base64,{base64.b64encode(audio).decode('ascii')}"
    result = get_fire().transcribe(data_url)
    del data_url, audio  # nothing of the clip outlives this call
    record_fire_call(user_id, result.price_usd)

    text = " ".join(str(result.data.get("text") or "").split())
    if not text:
        raise TranscriptionError("We didn't catch any speech; please try again", 422)
    return text
