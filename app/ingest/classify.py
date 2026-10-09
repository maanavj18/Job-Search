from __future__ import annotations

import re

_GREENHOUSE = re.compile(
    r"https?://(?:job-boards|boards)\.greenhouse\.io/([^/?#]+)/jobs/(\d+)",
    re.I,
)
_LEVER = re.compile(
    r"https?://jobs\.lever\.co/([^/?#]+)/([0-9a-fA-F-]{36})",
    re.I,
)
_ASHBY = re.compile(
    r"https?://jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-fA-F-]{36})",
    re.I,
)


def classify_url(url: str) -> tuple[str, str | None, str | None]:
    greenhouse = _GREENHOUSE.search(url)
    if greenhouse:
        return "greenhouse", greenhouse.group(1), greenhouse.group(2)
    lever = _LEVER.search(url)
    if lever:
        return "lever", lever.group(1), lever.group(2)
    ashby = _ASHBY.search(url)
    if ashby:
        return "ashby", ashby.group(1), ashby.group(2)
    return "manual", None, None


def choose_application(urls: list[str]) -> tuple[str, str, str | None, str | None]:
    fallback = ""
    for url in urls:
        ats, token, job_id = classify_url(url)
        if ats != "manual":
            return url, ats, token, job_id
        if not fallback and "simplify.jobs" not in url:
            fallback = url
    if fallback:
        return fallback, "manual", None, None
    if urls:
        return urls[0], "manual", None, None
    return "", "manual", None, None


def only_simplify(urls: list[str], ats: str) -> bool:
    return ats == "manual" and bool(urls) and all("simplify.jobs" in url for url in urls)
