"""Continue the job-applier improvement loop when a concrete next item is waiting."""

from __future__ import annotations

import json
import sys

from app.learn import session_context, stop_followup


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace").strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if "status" in payload and "loop_count" in payload:
        result = stop_followup(payload)
    elif "session_id" in payload:
        result = session_context()
    else:
        result = {}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
