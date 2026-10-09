from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path

from app.db import status_counts
from app.paths import data_dir, repo_root

_INFO_NOTES = (
    "Custom questions were not in the public posting.",
    "The page did not expose any fields.",
    "Browser question scan unavailable",
)
_SLUG = re.compile(r"[^a-z0-9]+")


def corrections_path() -> Path:
    return data_dir() / "corrections.jsonl"


def lessons_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".cursor" / "skills" / "job-applier" / "lessons.md"


def learn_next_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".cursor" / "learn-next.json"


def improve_enabled(root: Path | None = None) -> bool:
    return ((root or repo_root()) / ".cursor" / "improve.enabled").is_file()


def log_override(label: str, previous_source: str) -> None:
    if previous_source not in {"similar", "llm"}:
        return
    record = {
        "label": " ".join(label.split())[:300],
        "previous_source": previous_source,
    }
    path = corrections_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def load_corrections() -> list[dict]:
    path = corrections_path()
    if not path.exists():
        return []
    latest: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        label = str(item.get("label") or "").strip()
        source = str(item.get("previous_source") or "")
        if not label or source not in {"similar", "llm"}:
            continue
        latest[_slug(label)] = {"label": label, "previous_source": source}
    return list(latest.values())


def build_report(conn, corrections: list[dict], lessons: str) -> dict:
    failures: dict[str, list[str]] = defaultdict(list)
    for row in conn.execute(
        """
        SELECT company, ats, error FROM jobs
        WHERE status = 'failed' AND error IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 40
        """
    ):
        error = str(row["error"])
        key = _failure_key(error)
        label = f"{row['company']} ({row['ats']})"
        if label not in failures[key]:
            failures[key].append(label)
        failures[key + "\0error"] = [error[:180]]

    blanks: list[dict] = []
    checks: list[dict] = []
    extractions: dict[str, list[str]] = defaultdict(list)
    rows = conn.execute(
        """
        SELECT j.company, j.note, a.fields_json
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        WHERE j.status IN ('needs_review', 'opened')
        """
    )
    for row in rows:
        note = str(row["note"] or "")
        if note and not note.startswith(_INFO_NOTES):
            key = _failure_key(note)
            if row["company"] not in extractions[key]:
                extractions[key].append(row["company"])
            extractions[key + "\0error"] = [note[:180]]
        for field in json.loads(row["fields_json"]):
            label = str(field.get("label") or "").strip()
            value = str(field.get("value") or "").strip()
            if field.get("required") and not value and field.get("type") != "file":
                blanks.append({"company": row["company"], "label": label})
            if field.get("confidence") == "check" or field.get("source") == "similar":
                checks.append(
                    {
                        "company": row["company"],
                        "label": label,
                        "source": str(field.get("source") or ""),
                    }
                )

    open_items: list[dict] = []
    closed: list[str] = []
    seen: set[str] = set()

    def add(kind: str, key: str, summary: str) -> None:
        item_id = f"{kind}:{_slug(key)}"
        if item_id in seen:
            return
        seen.add(item_id)
        if item_id in lessons:
            closed.append(item_id)
            return
        if len(open_items) < 8:
            open_items.append({"id": item_id, "kind": kind, "summary": summary})

    for item in corrections:
        add(
            "override",
            item["label"],
            f'You replaced a {item["previous_source"]} draft for "{item["label"]}".',
        )
    for key, companies in list(failures.items()):
        if "\0" in key:
            continue
        error = failures[key + "\0error"][0]
        add("failure", key, f"{', '.join(companies[:4])} failed: {error}")
    for key, companies in list(extractions.items()):
        if "\0" in key:
            continue
        note = extractions[key + "\0error"][0]
        add("extraction", key, f"{', '.join(companies[:4])} form scan failed: {note}")

    return {
        "counts": status_counts(conn),
        "blank_required": blanks[:12],
        "checks": checks[:12],
        "open_items": open_items,
        "closed": closed[:8],
    }


def render_report(report: dict) -> str:
    lines = ["# Learn report", ""]
    counts = report["counts"]
    if counts:
        lines.append(
            "Queue: " + ", ".join(f"{name} {count}" for name, count in sorted(counts.items()))
        )
    else:
        lines.append("Queue: empty")
    lines.append("")
    lines.append("## Open items")
    if report["open_items"]:
        for item in report["open_items"]:
            lines.append(f"- `{item['id']}` {item['summary']}")
    else:
        lines.append("- None. Do not invent a code change.")
    lines.append("")
    lines.append("## Missing required facts")
    lines.append("Leave these blank. Do not invent them.")
    if report["blank_required"]:
        for field in report["blank_required"]:
            lines.append(f"- {field['company']}: {field['label']}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Answers flagged for a check")
    if report["checks"]:
        for field in report["checks"]:
            lines.append(f"- {field['company']}: {field['label']} ({field['source']})")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Already addressed")
    if report["closed"]:
        for item_id in report["closed"]:
            lines.append(f"- `{item_id}`")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def stop_followup(payload: dict, root: Path | None = None) -> dict:
    if payload.get("status") != "completed":
        return {}
    root = root or _project_root()
    if not improve_enabled(root):
        return {}
    path = learn_next_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not data.get("continue"):
        return {}
    item = str(data.get("item") or "").strip()
    if not item:
        return {}
    return {
        "followup_message": (
            "Improvement loop. Handle only this open item: "
            f"{item}\n\nFollow the Improve itself section of the job-applier skill. "
            "Make one code or skill change, add a regression test that does not use real profile answers, "
            "run pytest, and append a lesson that contains the item id and no personal facts. "
            "Then run python -m app.cli learn and rewrite .cursor/learn-next.json. "
            "Set continue to false when no open item remains, the failure is a removed posting, "
            "or the next step would invent a biography fact. Do not submit applications."
        )
    }


def session_context(root: Path | None = None) -> dict:
    root = root or _project_root()
    if not improve_enabled(root):
        return {}
    return {
        "additional_context": (
            "Job applier self-improvement is on. After you draft applications, or when the user "
            "asks you to improve the applier, follow the Improve itself section of the job-applier skill. "
            "Do not start an improvement cycle for an unrelated request."
        )
    }


def _project_root() -> Path:
    override = os.environ.get("CURSOR_PROJECT_DIR")
    if override:
        return Path(override)
    return repo_root()


def _slug(text: str) -> str:
    slug = _SLUG.sub("-", text.lower()).strip("-")
    return slug[:60] or "item"


def _failure_key(error: str) -> str:
    text = error.lower()
    if "404" in text or "not found" in text:
        return "http-404"
    if "429" in text or "rate limit" in text:
        return "http-429"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    head = re.split(r"[:\n]", error, maxsplit=1)[0].strip()
    return _slug(head) or "error"
