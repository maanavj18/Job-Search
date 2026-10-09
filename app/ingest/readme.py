from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


FLAG_CHARS = {
    "\U0001f6c2": "no_sponsorship",
    "\U0001f1fa\U0001f1f8": "us_citizenship",
    "\U0001f512": "closed",
    "\U0001f525": "faang",
    "\U0001f393": "advanced_degree",
}

CONTINUATIONS = {"↳", "->", "→", ""}
_AGE = re.compile(r"(\d+)\s*(d|w|mo)\b", re.I)
_HEADING = re.compile(r"^##\s+(.+)$", re.M)
_TABLE = re.compile(r"<table\b.*?</table>", re.I | re.S)
_IDENTITY_KEYS = {"for", "token"}


@dataclass
class Role:
    section: str
    company: str
    title: str
    location: str
    urls: list[str] = field(default_factory=list)
    age_text: str = ""
    age_days: int | None = None
    flags: dict[str, bool] = field(default_factory=dict)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict]] = []
        self._in_row = False
        self._in_cell = False
        self._parts: list[str] = []
        self._links: list[str] = []
        self._row: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "tr":
            self._in_row = True
            self._row = []
        elif tag == "td" and self._in_row:
            self._in_cell = True
            self._parts = []
            self._links = []
        elif tag == "a" and self._in_cell:
            href = attr.get("href")
            if href:
                self._links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_cell:
            text = " ".join("".join(self._parts).split())
            self._row.append({"text": text, "links": list(self._links)})
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if len(self._row) >= 4:
                self.rows.append(self._row)
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._parts.append(data)


def section_slug(heading: str) -> str:
    text = heading.lower()
    if "software engineering" in text:
        return "software-engineering"
    if "data science" in text or "machine learning" in text:
        return "data-science"
    if "product management" in text:
        return "product"
    if "quantitative" in text:
        return "quant"
    if "hardware" in text:
        return "hardware"
    return "other"


def parse_age(text: str) -> int | None:
    match = _AGE.search(text.strip().lower())
    if not match:
        return None
    count = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "d":
        return count
    if unit == "w":
        return count * 7
    return count * 30


def _flags(text: str) -> dict[str, bool]:
    found = {name: False for name in FLAG_CHARS.values()}
    for symbol, name in FLAG_CHARS.items():
        if symbol in text:
            found[name] = True
    return found


def _company_name(text: str) -> str:
    for symbol in FLAG_CHARS:
        text = text.replace(symbol, " ")
    return " ".join(text.split()).strip()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    query = ""
    if path.endswith("/embed/job_app"):
        query = urlencode(sorted((key, value) for key, value in parse_qsl(parts.query) if key in _IDENTITY_KEYS))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def parse_readme(text: str) -> list[Role]:
    headings = [(match.start(), section_slug(match.group(1))) for match in _HEADING.finditer(text)]
    roles: list[Role] = []
    for table in _TABLE.finditer(text):
        section = "other"
        for position, slug in headings:
            if position < table.start():
                section = slug
            else:
                break
        parser = _TableParser()
        parser.feed(table.group(0))
        parser.close()
        company = ""
        for row in parser.rows:
            raw_company = row[0]["text"]
            cleaned = _company_name(raw_company)
            if cleaned in CONTINUATIONS:
                cleaned = company
            else:
                company = cleaned
            if not cleaned:
                continue
            title = row[1]["text"]
            location = row[2]["text"] if len(row) > 2 else ""
            age_text = row[-1]["text"] if len(row) > 4 else ""
            urls: list[str] = []
            blob = " ".join(cell["text"] for cell in row)
            for cell in row:
                urls.extend(cell["links"])
            roles.append(
                Role(
                    section=section,
                    company=cleaned,
                    title=title,
                    location=location,
                    urls=_unique(urls),
                    age_text=age_text,
                    age_days=parse_age(age_text),
                    flags=_flags(blob),
                )
            )
    return roles


def _unique(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered
