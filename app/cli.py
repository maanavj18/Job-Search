from __future__ import annotations

import argparse
import sys

import httpx
import uvicorn

from app.audit import build_audit, render_audit
from app.config import load_answers, load_env, load_filters, load_profile, load_sources
from app.db import connect, finish_run, start_run, status_counts
from app.draft.pipeline import run_pipeline
from app.learn import build_report, lessons_path, load_corrections, render_report
from app.notify.email import send_digest
from app.paths import data_dir, repo_root
from app.web import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Fetch roles and draft applications")
    run.add_argument("--limit", type=int, default=0, help="Max new drafts this run. 0 drafts every new match.")
    run.add_argument("--skip-browser", action="store_true", help="Do not open Lever or Ashby pages while drafting.")
    run.add_argument("--serve", action="store_true", help="Start the review page after drafting.")

    serve = sub.add_parser("serve", help="Open the local review page")
    serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("learn", help="Summarize misses the agent can fix")
    sub.add_parser("audit", help="Check the app against what it should have produced")

    args = parser.parse_args(argv)
    load_env(repo_root())
    if args.command == "serve":
        _serve(args.port)
        return
    if args.command == "learn":
        _learn()
        return
    if args.command == "audit":
        _audit()
        return
    _run(args.limit, not args.skip_browser)
    if args.serve:
        _serve(8000)


def _run(limit: int, extract: bool) -> None:
    root = repo_root()
    profile, using_example = load_profile(root)
    if using_example:
        _out("Using the example profile. Copy profile/profile.example.yaml to profile/profile.yaml before real applications.")
    conn = connect()
    run_id = start_run(conn)
    try:
        with httpx.Client(
            headers={"User-Agent": "job-search-local/0.1"},
            follow_redirects=True,
            timeout=60,
        ) as client:
            summary = run_pipeline(
                conn=conn,
                sources=load_sources(root),
                filters=load_filters(root),
                profile=profile,
                answers=load_answers(root),
                client=client,
                limit=limit,
                extract=extract,
                log=_out,
            )
    except BaseException as exc:
        finish_run(conn, run_id, None, f"{type(exc).__name__}: {exc}")
        raise
    finish_run(conn, run_id, summary)
    if summary["new_drafts"]:
        try:
            if send_digest(summary["new_drafts"]):
                _out(f"Emailed a digest of {len(summary['new_drafts'])} draft(s).")
        except Exception as exc:
            _out(f"Email digest failed: {exc}")
    counts = status_counts(connect())
    _out(
        f"Parsed {summary['parsed']}. Drafted {summary['drafted']}. Failed {summary['failed']}."
    )
    _out(
        "Queue: "
        + ", ".join(
            f"{name} {counts.get(name, 0)}"
            for name in ("needs_review", "new", "manual", "skipped", "failed")
        )
    )
    _out("Review at http://127.0.0.1:8000")
    _out("Start the page with: python -m app.cli serve")


def _learn() -> None:
    root = repo_root()
    lessons = lessons_path(root)
    text = lessons.read_text(encoding="utf-8") if lessons.exists() else ""
    report = render_report(build_report(connect(), load_corrections(), text))
    path = data_dir() / "learn-report.md"
    path.write_text(report, encoding="utf-8")
    _out(report)
    _out(f"Wrote {path}")


def _audit() -> None:
    report = render_audit(build_audit(connect(), repo_root()))
    path = data_dir() / "audit-report.md"
    path.write_text(report, encoding="utf-8")
    _out(report)
    _out(f"Wrote {path}")


def _serve(port: int) -> None:
    _out(f"Review page at http://127.0.0.1:{port}")
    uvicorn.run(create_app(), host="127.0.0.1", port=port)


def _out(text: str) -> None:
    sys.stdout.buffer.write((str(text) + "\n").encode("utf-8", "replace"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
