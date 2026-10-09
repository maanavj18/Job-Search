from pathlib import Path

from app.ingest.classify import choose_application, classify_url, needs_resolve
from app.ingest.filters import skip_reason
from app.ingest.readme import canonical_url, parse_readme

FIXTURE = Path(__file__).parent / "fixtures" / "readme_snippet.html"


def test_parse_roles_flags_and_continuation():
    roles = parse_readme(FIXTURE.read_text(encoding="utf-8"))
    by_company = {role.company: role for role in roles}
    acme = next(role for role in roles if role.company == "Acme" and role.location == "Columbus, OH")
    remote = next(role for role in roles if role.company == "Acme" and role.location == "Remote")
    assert acme.section == "software-engineering"
    assert acme.flags["no_sponsorship"] is True
    assert acme.age_days == 0
    assert remote.company == "Acme"
    assert remote.flags["no_sponsorship"] is False
    assert remote.age_days == 1
    closed = by_company["Closed Co"]
    assert closed.flags["closed"] is True
    assert by_company["Citizen Co"].flags["us_citizenship"] is True
    assert by_company["Citizen Co"].age_days == 21
    assert by_company["Workday Co"].age_days == 30
    hardware = by_company["Hardware Co"]
    assert hardware.section == "hardware"


def test_choose_greenhouse_over_simplify_and_classify_apply_urls():
    roles = parse_readme(FIXTURE.read_text(encoding="utf-8"))
    acme = next(role for role in roles if role.location == "Columbus, OH")
    url, ats, token, job_id = choose_application(acme.urls)
    assert ats == "greenhouse"
    assert token == "acme"
    assert job_id == "123"
    assert "simplify.jobs" not in url
    lever = next(role for role in roles if role.location == "Remote")
    assert classify_url(lever.urls[0])[0] == "lever"
    closed = next(role for role in roles if role.company == "Closed Co")
    assert classify_url(closed.urls[0])[0] == "ashby"
    workday = next(role for role in roles if role.company == "Workday Co")
    assert choose_application(workday.urls)[1] == "manual"


def test_greenhouse_eu_and_embed_links_are_supported():
    eu = "https://job-boards.eu.greenhouse.io/acme/jobs/4955279101?utm_source=Simplify&ref=Simplify"
    assert classify_url(eu) == ("greenhouse", "acme", "4955279101")
    embed = "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=8168315"
    assert classify_url(embed) == ("greenhouse", "acme", "8168315")
    bare = "https://boards.greenhouse.io/embed/job_app?token=8168315&utm_source=Simplify"
    url, ats, _, _ = choose_application([bare])
    assert ats == "manual"
    assert needs_resolve([bare], url, ats)


def test_canonical_url_drops_tracking_but_keeps_job_identity():
    lever = "https://jobs.lever.co/acme/b18cc87d-fca2-485a-a0f2-ad6197db63f2/apply?utm_source=Simplify&ref=Simplify"
    assert canonical_url(lever) == "https://jobs.lever.co/acme/b18cc87d-fca2-485a-a0f2-ad6197db63f2/apply"
    first = canonical_url("https://boards.greenhouse.io/embed/job_app?token=1&utm_source=Simplify")
    second = canonical_url("https://boards.greenhouse.io/embed/job_app?token=2&utm_source=Simplify")
    assert first != second


def test_filters_skip_closed_sponsorship_citizenship_and_section():
    roles = parse_readme(FIXTURE.read_text(encoding="utf-8"))
    filters = {"sections": ["software-engineering"], "max_age_days": None}
    profile = {"us_citizen": False, "needs_sponsorship": True, "has_advanced_degree": False}
    reasons = {role.company + role.location: skip_reason(role, profile, filters) for role in roles}
    assert reasons["AcmeColumbus, OH"] == "Does not offer sponsorship"
    assert reasons["Closed CoNYC"] == "Listing is marked closed"
    assert reasons["Citizen CoDC"] == "Requires U.S. citizenship"
    assert reasons["Hardware CoAustin, TX"] == "Outside your selected sections"
    assert reasons["Workday CoTX"] is None
