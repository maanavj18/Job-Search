from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.paths import data_dir


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  dedupe_key TEXT UNIQUE NOT NULL,
  source TEXT NOT NULL,
  section TEXT,
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT,
  url TEXT,
  urls_json TEXT NOT NULL,
  ats TEXT NOT NULL,
  ats_token TEXT,
  ats_job_id TEXT,
  age_text TEXT,
  age_days INTEGER,
  flags_json TEXT NOT NULL,
  status TEXT NOT NULL,
  skip_reason TEXT,
  error TEXT,
  note TEXT,
  discovered_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY,
  job_id INTEGER UNIQUE NOT NULL REFERENCES jobs(id),
  fields_json TEXT NOT NULL,
  status TEXT NOT NULL,
  drafted_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  parsed INTEGER,
  drafted INTEGER,
  failed INTEGER,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

LOCKED_STATUSES = {"needs_review", "opened", "submitted"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or (data_dir() / "jobs.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_job(conn: sqlite3.Connection, job: dict) -> str:
    existing = conn.execute(
        "SELECT id, status FROM jobs WHERE dedupe_key = ?",
        (job["dedupe_key"],),
    ).fetchone()
    timestamp = now()
    if existing is None:
        conn.execute(
            """
            INSERT INTO jobs (
              dedupe_key, source, section, company, title, location, url, urls_json,
              ats, ats_token, ats_job_id, age_text, age_days, flags_json, status,
              skip_reason, error, note, discovered_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["dedupe_key"],
                job["source"],
                job["section"],
                job["company"],
                job["title"],
                job["location"],
                job["url"],
                json.dumps(job["urls"]),
                job["ats"],
                job.get("ats_token"),
                job.get("ats_job_id"),
                job.get("age_text"),
                job.get("age_days"),
                json.dumps(job.get("flags") or {}),
                job["status"],
                job.get("skip_reason"),
                None,
                None,
                timestamp,
                timestamp,
            ),
        )
        return "inserted"
    if existing["status"] in LOCKED_STATUSES:
        conn.execute(
            """
            UPDATE jobs
            SET age_text = ?, age_days = ?, updated_at = ?
            WHERE id = ?
            """,
            (job.get("age_text"), job.get("age_days"), timestamp, existing["id"]),
        )
        return "kept"
    conn.execute(
        """
        UPDATE jobs
        SET section = ?, company = ?, title = ?, location = ?, url = ?, urls_json = ?,
            ats = ?, ats_token = ?, ats_job_id = ?, age_text = ?, age_days = ?,
            flags_json = ?, status = ?, skip_reason = ?, error = NULL, updated_at = ?
        WHERE id = ?
        """,
        (
            job["section"],
            job["company"],
            job["title"],
            job["location"],
            job["url"],
            json.dumps(job["urls"]),
            job["ats"],
            job.get("ats_token"),
            job.get("ats_job_id"),
            job.get("age_text"),
            job.get("age_days"),
            json.dumps(job.get("flags") or {}),
            job["status"],
            job.get("skip_reason"),
            timestamp,
            existing["id"],
        ),
    )
    return "updated"


def jobs_to_draft(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'new'
              AND ats IN ('greenhouse', 'lever', 'ashby')
            ORDER BY COALESCE(age_days, 9999), id
            """
        )
    )


def save_application(conn: sqlite3.Connection, job_id: int, fields: list[dict], status: str) -> None:
    timestamp = now()
    payload = json.dumps(fields)
    existing = conn.execute(
        "SELECT id FROM applications WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO applications (job_id, fields_json, status, drafted_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, payload, status, timestamp, timestamp),
        )
    else:
        conn.execute(
            """
            UPDATE applications
            SET fields_json = ?, status = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (payload, status, timestamp, job_id),
        )
    conn.execute(
        "UPDATE jobs SET status = ?, error = NULL, updated_at = ? WHERE id = ?",
        (status, timestamp, job_id),
    )


def mark_failed(conn: sqlite3.Connection, job_id: int, error: str) -> None:
    conn.execute(
        "UPDATE jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
        (error[:2000], now(), job_id),
    )


def get_application(conn: sqlite3.Connection, application_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT a.*, j.company, j.title, j.location, j.url, j.ats, j.age_text, j.note, j.error,
               j.status AS job_status
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        WHERE a.id = ?
        """,
        (application_id,),
    ).fetchone()


def list_jobs(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return list(
            conn.execute(
                """
                SELECT j.*, a.id AS application_id
                FROM jobs j
                LEFT JOIN applications a ON a.job_id = j.id
                WHERE j.status = ?
                ORDER BY COALESCE(j.age_days, 9999), j.company, j.title
                """,
                (status,),
            )
        )
    return list(
        conn.execute(
            """
            SELECT j.*, a.id AS application_id
            FROM jobs j
            LEFT JOIN applications a ON a.job_id = j.id
            ORDER BY COALESCE(j.age_days, 9999), j.company, j.title
            """
        )
    )


def start_run(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (now(),))
    conn.commit()
    return int(cursor.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, summary: dict | None, error: str | None = None) -> None:
    summary = summary or {}
    conn.execute(
        "UPDATE runs SET finished_at = ?, parsed = ?, drafted = ?, failed = ?, error = ? WHERE id = ?",
        (
            now(),
            summary.get("parsed"),
            summary.get("drafted"),
            summary.get("failed"),
            error[:2000] if error else None,
            run_id,
        ),
    )
    conn.commit()


def last_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
    return {row["status"]: row["n"] for row in rows}
