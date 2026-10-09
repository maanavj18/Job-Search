"""Check the app against what it should have produced. Findings never contain answer text."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from app.config import load_profile
from app.db import last_run
from app.draft.profile_map import draft_fields
from app.draft.questions import empty_field
from app.paths import repo_root

SUPPORTED_ATS = ("greenhouse", "lever", "ashby")
_SEVERITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_SLUG = re.compile(r"[^a-z0-9]+")

FAKE_PROFILE = {
    "first_name": "Alex",
    "last_name": "Example",
    "email": "alex@example.test",
    "phone": "+1-555-0100",
    "linkedin": "https://www.linkedin.com/in/example",
    "school": "Example State University",
    "degree": "Bachelor of Science",
    "major": "Computer Science",
    "graduation": "May 2027",
    "gpa": "",
    "work_authorized": True,
    "needs_sponsorship": False,
    "address": {"city": "Columbus", "state": "OH", "country": "United States"},
    "eeo": {},
}

# Labels that ask something other than the profile fact their keywords suggest.
MUST_NOT_FILL = (
    "Please state why you are interested in this role",
    "Are you currently enrolled in school?",
    "Have you graduated?",
    "Which country are you authorized to work in?",
    "Can we email you about future openings?",
    "Do you understand this role does not offer visa sponsorship?",
    "In what capacity have you used Python?",
    "Undergraduate GPA",
    "What major challenges have you faced on a team project?",
    "To what degree are you comfortable with on-call work?",
    "What year did you attend the career fair?",
)

# Labels that must still be filled, so a fix cannot pass by blanking everything.
MUST_FILL = {
    "First Name": "Alex",
    "Email": "alex@example.test",
    "What is your email address?": "alex@example.test",
    "School": "Example State University",
    "When do you expect to graduate?": "May 2027",
    "Will you now or in the future require sponsorship?": "No",
    "Are you legally authorized to work in the United States?": "Yes",
    "City": "Columbus",
    "LinkedIn Profile": "https://www.linkedin.com/in/example",
}


def answer_safety() -> list[dict]:
    labels = list(MUST_NOT_FILL) + list(MUST_FILL)
    fields = [empty_field(key=str(index), label=label) for index, label in enumerate(labels)]
    draft_fields(fields, FAKE_PROFILE, [], use_llm=False)
    problems: list[dict] = []
    for field in fields:
        label = field["label"]
        value = str(field.get("value") or "")
        if label in MUST_FILL:
            if value != MUST_FILL[label]:
                problems.append({"label": label, "kind": "missed"})
        elif value and field.get("source") == "profile":
            problems.append({"label": label, "kind": "misfill"})
    return problems


def build_audit(conn, root: Path | None = None) -> list[dict]:
    root = root or repo_root()
    findings: list[dict] = []

    def add(item_id: str, severity: str, area: str, summary: str, needs_user: bool = False) -> None:
        findings.append(
            {
                "id": item_id,
                "severity": severity,
                "area": area,
                "summary": summary,
                "needs_user": needs_user,
            }
        )

    run = last_run(conn)
    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    if run is None and job_count:
        add("run:no-record", "P1", "outcome", "Jobs exist but no run was recorded, so nobody can tell whether the last run finished.")
    elif run is not None and run["finished_at"] is None:
        add("run:unfinished", "P0", "outcome", f"Run {run['id']} started {run['started_at']} and never finished. Ignore this only while a run is in progress.")
    elif run is not None and run["error"]:
        add("run:error", "P0", "outcome", f"Run {run['id']} ended with an error: {str(run['error'])[:180]}")

    placeholders = ",".join("?" for _ in SUPPORTED_ATS)
    stuck = conn.execute(
        f"""
        SELECT COUNT(*) FROM jobs j
        LEFT JOIN applications a ON a.job_id = j.id
        WHERE j.status = 'new' AND j.ats IN ({placeholders}) AND a.id IS NULL
        """,
        SUPPORTED_ATS,
    ).fetchone()[0]
    if stuck:
        add("run:stuck-new", "P0", "outcome", f"{stuck} supported job(s) were ingested but never drafted.")

    hosts = Counter(
        urlsplit(str(row[0] or "")).netloc.lower()
        for row in conn.execute("SELECT url FROM jobs WHERE status = 'manual'")
    )
    for host, count in hosts.items():
        if any(name in host for name in SUPPORTED_ATS):
            add(f"classify:{_slug(host)}", "P1", "ingest", f"{count} job(s) on {host} were classified manual.")
    manual = sum(hosts.values())
    if job_count and manual / job_count > 0.5:
        top = ", ".join(f"{host} {count}" for host, count in hosts.most_common(5))
        add(
            "coverage:manual-share",
            "P2",
            "scope",
            f"{manual} of {job_count} jobs are manual. Top hosts: {top}. Adding a board is a scope decision.",
            needs_user=True,
        )

    for problem in answer_safety():
        if problem["kind"] == "misfill":
            add(f"misfill:{_slug(problem['label'])}", "P0", "answers", f'"{problem["label"]}" gets a profile fact it did not ask for.')
        else:
            add(f"missed:{_slug(problem['label'])}", "P1", "answers", f'"{problem["label"]}" is no longer filled from the profile.')

    _, using_example = load_profile(root)
    if using_example:
        add("setup:profile", "P1", "setup", "profile/profile.yaml is missing, so drafts use the example person.", needs_user=True)
    else:
        profile, _ = load_profile(root)
        resume = str(profile.get("resume_path") or "").strip()
        if not resume or not Path(resume).is_file():
            add("setup:resume", "P1", "setup", "resume_path is empty or the file does not exist.", needs_user=True)
    if not (root / ".git").exists():
        add("setup:git", "P1", "process", "The repo is not under version control, so loop edits cannot be reviewed or reverted.")

    findings.sort(key=lambda item: (_SEVERITY[item["severity"]], item["needs_user"], item["id"]))
    return findings


def render_audit(findings: list[dict]) -> str:
    lines = ["# Audit report", ""]
    agent = [item for item in findings if not item["needs_user"]]
    user = [item for item in findings if item["needs_user"]]
    lines.append("## Agent-fixable")
    if agent:
        lines.extend(f"- {item['severity']} `{item['id']}` {item['summary']}" for item in agent)
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Needs the user")
    if user:
        lines.extend(f"- {item['severity']} `{item['id']}` {item['summary']}" for item in user)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")[:60] or "item"
