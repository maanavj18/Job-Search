import json

from fastapi.testclient import TestClient

from app.db import connect, mark_failed, save_application, upsert_job
from app.draft.questions import empty_field
from app.learn import build_report, load_corrections, log_override, render_report, stop_followup
from app.web import create_app


def _job(conn, company: str, url: str) -> int:
    upsert_job(
        conn,
        {
            "dedupe_key": url,
            "source": "fixture",
            "section": "software-engineering",
            "company": company,
            "title": "Intern",
            "location": "Columbus, OH",
            "url": url,
            "urls": [],
            "ats": "greenhouse",
            "ats_token": "acme",
            "ats_job_id": "1",
            "age_text": "0d",
            "age_days": 0,
            "flags": {},
            "status": "new",
            "skip_reason": None,
        },
    )
    conn.commit()
    return int(conn.execute("SELECT id FROM jobs WHERE dedupe_key = ?", (url,)).fetchone()["id"])


def test_override_is_an_open_item_without_storing_the_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBSEARCH_DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "repo"
    (root / "profile").mkdir(parents=True)
    conn = connect(tmp_path / "jobs.sqlite")
    job_id = _job(conn, "Acme", "https://job-boards.greenhouse.io/acme/jobs/1")
    field = empty_field(key="why", label="Why this role?", field_type="textarea")
    field["source"] = "similar"
    field["value"] = "A guessed draft"
    save_application(conn, job_id, [field], "needs_review")
    conn.commit()
    app_id = conn.execute("SELECT id FROM applications").fetchone()["id"]
    client = TestClient(create_app(tmp_path / "jobs.sqlite", root))
    saved = client.post(
        f"/applications/{app_id}",
        data={"action": "save", "value_0": "A corrected draft"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    raw = (tmp_path / "data" / "corrections.jsonl").read_text(encoding="utf-8")
    assert "A guessed draft" not in raw
    assert "A corrected draft" not in raw
    report = build_report(conn, load_corrections(), "")
    assert report["open_items"][0]["id"] == "override:why-this-role"
    assert "A corrected draft" not in render_report(report)


def test_addressed_items_and_removed_postings_do_not_reopen(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBSEARCH_DATA_DIR", str(tmp_path / "data"))
    log_override("Why this role?", "llm")
    conn = connect(tmp_path / "jobs.sqlite")
    first = _job(conn, "Acme", "https://job-boards.greenhouse.io/acme/jobs/1")
    second = _job(conn, "Beta", "https://job-boards.greenhouse.io/beta/jobs/2")
    mark_failed(conn, first, "Client error '404 Not Found' for url 'https://example.test/1'")
    mark_failed(conn, second, "404 Client Error: Not Found for url 'https://example.test/2'")
    conn.commit()
    lessons = "Reviewed `failure:http-404` and `override:why-this-role`. No code change."
    report = build_report(conn, load_corrections(), lessons)
    assert report["open_items"] == []
    assert "failure:http-404" in report["closed"]
    assert "override:why-this-role" in report["closed"]


def test_required_blanks_are_listed_and_not_actionable(tmp_path):
    conn = connect(tmp_path / "jobs.sqlite")
    job_id = _job(conn, "Acme", "https://job-boards.greenhouse.io/acme/jobs/1")
    field = empty_field(key="gpa", label="GPA", required=True)
    save_application(conn, job_id, [field], "needs_review")
    conn.commit()
    report = build_report(conn, [], "")
    assert report["open_items"] == []
    assert report["blank_required"] == [{"company": "Acme", "label": "GPA"}]


def test_stop_hook_continues_only_for_a_waiting_item(tmp_path):
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    payload = {"status": "completed", "loop_count": 0}
    assert stop_followup(payload, tmp_path) == {}
    (cursor / "improve.enabled").write_text("on", encoding="utf-8")
    assert stop_followup({"status": "aborted", "loop_count": 0}, tmp_path) == {}
    (cursor / "learn-next.json").write_text(
        json.dumps({"continue": True, "item": "failure:timeout Fix the scan timeout."}),
        encoding="utf-8",
    )
    result = stop_followup(payload, tmp_path)
    assert "failure:timeout" in result["followup_message"]
    (cursor / "learn-next.json").write_text(json.dumps({"continue": False}), encoding="utf-8")
    assert stop_followup(payload, tmp_path) == {}
