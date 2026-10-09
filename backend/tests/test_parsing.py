import pytest

from app.services.parsing import ParseError, extract_text, validate_text

LONG = "Ada Lovelace\n\n\n\nSoftware engineer   with ten years of experience in Python."


def test_cleans_text():
    assert validate_text(LONG) == (
        "Ada Lovelace\n\nSoftware engineer with ten years of experience in Python."
    )


def test_txt_upload():
    assert extract_text("cv.txt", LONG.encode()).startswith("Ada Lovelace")


def test_rejects_short_and_unknown():
    with pytest.raises(ParseError):
        validate_text("too short")
    with pytest.raises(ParseError):
        extract_text("cv.docx", LONG.encode())


def test_rejects_broken_pdf():
    with pytest.raises(ParseError):
        extract_text("cv.pdf", b"%PDF-1.4 garbage")
