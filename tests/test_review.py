import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import load_answers
from app.db import connect, save_application, upsert_job
from app.draft.questions import empty_field
from app.web import create_app

README = Path(__file__).parent / "fixtures" / "readme_snippet.html"


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return _Response(self.payload)


def test_pipeline_drafts_supported_roles_once(tmp_path):
    from app.draft.pipeline import run_pipeline

    payload = json.loads((Path(__file__).parent / "fixtures" / "greenhouse_questions.json").read_text(encoding="utf-8"))
    db_path = tmp_path / "jobs.sqlite"
    conn = connect(db_path)
    profile = {
        "first_name": "Alex",
        "email": "alex@example.com",
        "needs_sponsorship": False,
        "us_citizen": True,
        "has_advanced_degree": False,
        "work_authorized": True,
        "eeo": {"gender": "decline"},
        "address": {},
        "gpa": "",
        "resume_path": "",
    }
    filters = {"sections": ["software-engineering"], "max_age_days": None}
    client = _Client(payload)
    text = README.read_text(encoding="utf-8")
    first = run_pipeline(
        conn=conn,
        sources=[{"name": "fixture", "url": "memory"}],
        filters=filters,
        profile=profile,
        answers=[],
        client=client,
        extract=False,
        fetch_text=lambda url: text,
        log=lambda message: None,
    )
    assert first["parsed"] == 6
    assert first["drafted"] == 3
    second = run_pipeline(
        conn=conn,
        sources=[{"name": "fixture", "url": "memory"}],
        filters=filters,
        profile=profile,
        answers=[],
        client=client,
        extract=False,
        fetch_text=lambda url: text,
        log=lambda message: None,
    )
    assert second["drafted"] == 0
    statuses = {
        row["company"]: row["status"]
        for row in conn.execute("SELECT company, status FROM jobs")
    }
    assert statuses["Acme"] in {"needs_review"}
    assert statuses["Closed Co"] == "skipped"
    assert statuses["Workday Co"] == "manual"
    assert statuses["Hardware Co"] == "skipped"


def test_review_save_writes_answer_bank(tmp_path):
    root = tmp_path / "repo"
    (root / "profile").mkdir(parents=True)
    db_path = tmp_path / "jobs.sqlite"
    conn = connect(db_path)
    upsert_job(
        conn,
        {
            "dedupe_key": "https://job-boards.greenhouse.io/acme/jobs/123",
            "source": "fixture",
            "section": "software-engineering",
            "company": "Acme",
            "title": "Intern",
            "location": "Columbus, OH",
            "url": "https://job-boards.greenhouse.io/acme/jobs/123",
            "urls": [],
            "ats": "greenhouse",
            "ats_token": "acme",
            "ats_job_id": "123",
            "age_text": "0d",
            "age_days": 0,
            "flags": {},
            "status": "new",
            "skip_reason": None,
        },
    )
    conn.commit()
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    fields = [
        empty_field(key="why", label="Why do you want to work here?", field_type="textarea"),
        empty_field(key="first_name", label="First Name"),
    ]
    fields[0]["source"] = "blank"
    save_application(conn, job_id, fields, "needs_review")
    conn.commit()
    app_id = conn.execute("SELECT id FROM applications").fetchone()["id"]
    client = TestClient(create_app(db_path, root))
    page = client.get(f"/applications/{app_id}")
    assert page.status_code == 200
    assert "Acme" in page.text
    assert "Submit application" not in page.text
    saved = client.post(
        f"/applications/{app_id}",
        data={"action": "save", "value_0": "I like building reliable software.", "value_1": "Alex"},
        follow_redirects=True,
    )
    assert saved.status_code == 200
    answers = load_answers(root)
    assert answers[0]["answer"] == "I like building reliable software."
    stored = json.loads(conn.execute("SELECT fields_json FROM applications").fetchone()["fields_json"])
    assert stored[1]["value"] == "Alex"
    assert all(item["question"] != "First Name" for item in answers)
