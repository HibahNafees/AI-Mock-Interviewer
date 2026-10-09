"""Turn uploaded résumés and job descriptions into plain text."""

import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MIN_CHARS = 50
MAX_CHARS = 30_000


class ParseError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_to_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("This PDF is password-protected; upload an unlocked copy")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError, KeyError) as err:
        raise ParseError(
            "Could not read this PDF; try pasting the text instead"
        ) from err


def extract_text(filename: str, data: bytes) -> str:
    """Text from an uploaded file (.pdf, .txt or .md). The file itself is not kept."""
    name = filename.lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        text = pdf_to_text(data)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise ParseError("Upload a PDF or a .txt file, or paste the text")
    return validate_text(text)


def validate_text(text: str) -> str:
    text = clean_text(text)
    if len(text) < MIN_CHARS:
        raise ParseError(
            "That document is too short to use (a scanned PDF has no text; paste it instead)"
        )
    return text[:MAX_CHARS]
