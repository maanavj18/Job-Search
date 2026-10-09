from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.apply.fill import spawn_fill
from app.config import load_profile, upsert_answer
from app.db import connect, get_application, list_jobs, now, status_counts
from app.draft.bank import is_identity
from app.learn import log_override
from app.paths import data_dir, repo_root

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TABS = [
    ("needs_review", "To review"),
    ("manual", "Manual"),
    ("opened", "Opened"),
    ("submitted", "Submitted"),
    ("skipped", "Skipped"),
    ("failed", "Failed"),
]


def create_app(db_path: Path | None = None, root: Path | None = None) -> FastAPI:
    app = FastAPI(title="Job Search")
    app.state.db_path = db_path or (data_dir() / "jobs.sqlite")
    app.state.root = root or repo_root()

    @app.get("/")
    def index(request: Request, status: str = "needs_review"):
        conn = connect(app.state.db_path)
        counts = status_counts(conn)
        jobs = [dict(job) for job in list_jobs(conn, status)]
        _, using_example = load_profile(app.state.root)
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "jobs": jobs,
                "status": status,
                "counts": counts,
                "tabs": TABS,
                "using_example": using_example,
            },
        )

    @app.get("/applications/{application_id}")
    def detail(request: Request, application_id: int):
        conn = connect(app.state.db_path)
        row = get_application(conn, application_id)
        if row is None:
            raise HTTPException(status_code=404)
        _, using_example = load_profile(app.state.root)
        return TEMPLATES.TemplateResponse(
            request,
            "detail.html",
            {
                "application": dict(row),
                "fields": json.loads(row["fields_json"]),
                "using_example": using_example,
                "saved": request.query_params.get("saved"),
                "opened": request.query_params.get("opened"),
            },
        )

    @app.post("/applications/{application_id}")
    async def update(request: Request, application_id: int):
        form = await request.form()
        action = str(form.get("action") or "save")
        conn = connect(app.state.db_path)
        row = get_application(conn, application_id)
        if row is None:
            raise HTTPException(status_code=404)
        if action == "skip":
            _set_status(conn, row, "skipped", skip_reason="Skipped in review")
            return RedirectResponse("/?status=skipped", status_code=303)
        if action == "submitted":
            _set_status(conn, row, "submitted", submitted=True)
            return RedirectResponse("/?status=submitted", status_code=303)
        fields = json.loads(row["fields_json"])
        _apply_form(fields, form, app.state.root)
        timestamp = now()
        status = "opened" if action == "open" else "needs_review"
        conn.execute(
            "UPDATE applications SET fields_json = ?, status = ?, updated_at = ? WHERE id = ?",
            (json.dumps(fields), status, timestamp, application_id),
        )
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, timestamp, row["job_id"]),
        )
        conn.commit()
        if action == "open":
            spawn_fill(application_id)
            return RedirectResponse(f"/applications/{application_id}?opened=1", status_code=303)
        return RedirectResponse(f"/applications/{application_id}?saved=1", status_code=303)

    return app


def _apply_form(fields: list[dict], form, root: Path) -> None:
    for index, field in enumerate(fields):
        if field.get("type") == "file" and f"value_{index}" not in form:
            continue
        new_value = str(form.get(f"value_{index}", "")).strip()
        old_value = str(field.get("value") or "").strip()
        source = field.get("source")
        field["value"] = new_value
        if not new_value or is_identity(field.get("label", "")):
            continue
        changed = new_value != old_value
        if changed or source in {"llm", "similar", "blank"}:
            upsert_answer(field["label"], new_value, root)
        if changed:
            log_override(field["label"], str(source or ""))
            field["source"] = "user"
            field["confidence"] = "high"
            field["notes"] = "Saved from your review."


def _set_status(conn, row, status: str, skip_reason: str | None = None, submitted: bool = False) -> None:
    timestamp = now()
    conn.execute(
        "UPDATE jobs SET status = ?, skip_reason = ?, updated_at = ? WHERE id = ?",
        (status, skip_reason, timestamp, row["job_id"]),
    )
    submitted_at = timestamp if submitted else None
    conn.execute(
        "UPDATE applications SET status = ?, updated_at = ?, submitted_at = COALESCE(?, submitted_at) WHERE id = ?",
        (status, timestamp, submitted_at, row["id"]),
    )
    conn.commit()


app = create_app()
