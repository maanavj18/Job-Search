from app.audit import answer_safety, build_audit
from app.db import connect, finish_run, start_run, upsert_job


def _job(conn, url: str, ats: str, status: str) -> None:
    upsert_job(
        conn,
        {
            "dedupe_key": url,
            "source": "fixture",
            "section": "software-engineering",
            "company": "Acme",
            "title": "Intern",
            "location": "Remote",
            "url": url,
            "urls": [url],
            "ats": ats,
            "ats_token": None,
            "ats_job_id": None,
            "age_text": "0d",
            "age_days": 0,
            "flags": {},
            "status": status,
            "skip_reason": None,
        },
    )
    conn.commit()


def _ids(conn, root) -> set[str]:
    return {item["id"] for item in build_audit(conn, root)}


def test_audit_flags_stuck_jobs_and_unfinished_runs(tmp_path):
    conn = connect(tmp_path / "jobs.sqlite")
    _job(conn, "https://job-boards.greenhouse.io/acme/jobs/1", "greenhouse", "new")
    _job(conn, "https://job-boards.eu.greenhouse.io/acme/jobs/2", "manual", "manual")
    ids = _ids(conn, tmp_path)
    assert "run:stuck-new" in ids
    assert "run:no-record" in ids
    assert "classify:job-boards-eu-greenhouse-io" in ids
    run_id = start_run(conn)
    assert "run:unfinished" in _ids(conn, tmp_path)
    finish_run(conn, run_id, {"parsed": 2, "drafted": 0, "failed": 0})
    ids = _ids(conn, tmp_path)
    assert not {"run:unfinished", "run:no-record", "run:error"} & ids


def test_question_labels_never_get_unrelated_profile_facts():
    assert answer_safety() == []


def test_audit_flags_a_run_that_raised(tmp_path):
    conn = connect(tmp_path / "jobs.sqlite")
    finish_run(conn, start_run(conn), None, "KeyboardInterrupt: ")
    assert "run:error" in _ids(conn, tmp_path)
