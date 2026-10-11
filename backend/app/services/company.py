"""Company research: read a company's public page and prepare "Why us?" questions.

The server fetches a URL the user typed, so it must never reach internal
systems (SSRF): http(s) on ports 80/443 only, every resolved address and the
connected peer must be public, redirects are followed by hand and re-checked,
and the body is size- and time-limited. The page text is untrusted data.
"""

import hashlib
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
from pydantic import BaseModel, Field

from ..extensions import db
from ..models import CompanyResearch
from .llm import chat_json, render
from .scoring import SYSTEM

TIMEOUT_SEC = 8
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 3
MAX_TEXT = 6000
MIN_TEXT = 300
FALLBACK_PATHS = ("/about", "/about-us", "/careers")
USER_AGENT = "InterVox/1.0 (company research for interview prep)"


class ResearchError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class ResearchOut(BaseModel):
    company: str = Field(default="", max_length=160)
    summary: str = Field(default="", max_length=600)
    talking_points: list[str] = Field(default_factory=list, max_length=6)
    why_us_questions: list[str] = Field(default_factory=list, max_length=4)


class _Text(HTMLParser):
    """Visible text from HTML (skips scripts, styles and navigation chrome)."""

    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "head", "form"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def html_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    return " ".join(" ".join(p.parts).split())[:MAX_TEXT]


def _public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return addr.is_global and not addr.is_multicast


def check_url(url: str) -> str:
    """The normalized URL if it's safe to fetch, else ResearchError."""
    url = url.strip()
    if "://" not in url:
        url = f"https://{url}"
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ResearchError("Enter the company's website, e.g. https://example.com")
    if parts.username or parts.password:
        raise ResearchError("That link isn't a plain website address")
    if parts.port not in (None, 80, 443):
        raise ResearchError("Only standard website addresses are supported")
    try:
        infos = socket.getaddrinfo(
            parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror:
        raise ResearchError("We couldn't find that website") from None
    if not infos or not all(_public(i[4][0]) for i in infos):
        raise ResearchError("That address isn't a public website")
    return url


def _get(url: str) -> str:
    """Fetch one public HTML page, following redirects only to public sites."""
    for _ in range(MAX_REDIRECTS + 1):
        url = check_url(url)
        try:
            r = requests.get(
                url,
                timeout=TIMEOUT_SEC,
                allow_redirects=False,
                stream=True,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            )
        except requests.RequestException:
            raise ResearchError("We couldn't open that website") from None
        try:
            sock = r.raw._connection.sock if r.raw._connection else None
            peer = sock.getpeername()[0] if sock else None
            if peer and not _public(peer):  # DNS changed between check and connect
                raise ResearchError("That address isn't a public website")
            if r.is_redirect:
                url = urljoin(url, r.headers.get("Location", ""))
                continue
            if r.status_code >= 400:
                raise ResearchError("That page didn't load (it may need a login)")
            if "html" not in r.headers.get("Content-Type", "").lower():
                raise ResearchError("That link isn't a web page")
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            return body[:MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")
        finally:
            r.close()
    raise ResearchError("That website redirects too many times")


def _page_text(url: str) -> str:
    text = html_text(_get(url))
    if len(text) >= MIN_TEXT:
        return text
    origin = f"{urlparse(check_url(url)).scheme}://{urlparse(check_url(url)).netloc}"
    for path in FALLBACK_PATHS:
        try:
            more = html_text(_get(origin + path))
        except ResearchError:
            continue
        if len(more) >= MIN_TEXT:
            return more
    return text


def research(user_id: int, url: str, role: str) -> CompanyResearch:
    url = check_url(url)
    key = hashlib.sha256(url.lower().rstrip("/").encode()).hexdigest()
    cached = db.session.scalar(db.select(CompanyResearch).filter_by(url_key=key))
    if cached is not None:
        return cached
    page = _page_text(url)
    if len(page) < 100:
        raise ResearchError(
            "That page has too little text to learn from; try its About page"
        )
    out = chat_json(
        user_id,
        render("company_research", role=role, url=url, page=page),
        ResearchOut,
        SYSTEM,
        max_tokens=800,
        temperature=0.3,
    )
    if not out.company or not out.why_us_questions:
        raise ResearchError(
            "That page doesn't say enough about the company; try its About page"
        )
    row = CompanyResearch(
        url_key=key,
        url=url[:500],
        result_json={
            "company": out.company.strip(),
            "summary": out.summary.strip(),
            "talking_points": [t.strip() for t in out.talking_points if t.strip()][:5],
            "why_us_questions": [q.strip() for q in out.why_us_questions if q.strip()][
                :3
            ],
        },
    )
    db.session.add(row)
    db.session.commit()
    return row


def research_dict(row: CompanyResearch) -> dict:
    return {"id": row.id, "url": row.url, **row.result_json}
