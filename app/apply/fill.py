from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from app.db import connect, get_application, now
from app.paths import data_dir

log = logging.getLogger("jobsearch.fill")


def fill_fields(page, fields: list[dict]) -> list[str]:
    """Fill visible answers. This function must not click Submit or press Enter."""
    notes: list[str] = []
    page.set_default_timeout(5000)
    try:
        page.wait_for_selector("input, textarea, select", timeout=8000)
    except Exception:
        notes.append("The form did not finish loading.")
    for field in fields:
        value = str(field.get("value") or "").strip()
        label = str(field.get("label") or "").strip()
        if not label or not value:
            continue
        if field.get("type") == "file":
            notes.extend(_fill_file(page, label, str(field.get("key") or ""), value))
            continue
        try:
            _fill_one(page, field, value)
        except Exception as exc:
            message = str(exc).split("Call log:", 1)[0].strip()
            notes.append(f"{label}: {message[:180]}")
        page.wait_for_timeout(200)
    notes.extend(_repair_text(page, fields))
    return notes


def _repair_text(page, fields: list[dict]) -> list[str]:
    """Greenhouse can clear an earlier text field when a later one is edited."""
    notes: list[str] = []
    for field in fields:
        value = str(field.get("value") or "").strip()
        label = str(field.get("label") or "").strip()
        if not value or not label or field.get("type") in {"file", "select", "multi", "boolean"}:
            continue
        locator = _locate(page, str(field.get("key") or ""), label)
        if locator is None or locator.get_attribute("role") == "combobox":
            continue
        actual = locator.input_value()
        if _same_text(actual, value):
            continue
        try:
            _type_into(locator, value)
        except Exception as exc:
            notes.append(f"{label}: {exc}")
    return notes


def _same_text(actual: str, expected: str) -> bool:
    if actual.strip() == expected.strip():
        return True
    expected_digits = "".join(character for character in expected if character.isdigit())
    actual_digits = "".join(character for character in actual if character.isdigit())
    return len(expected_digits) >= 7 and expected_digits == actual_digits


def _fill_file(page, label: str, key: str, value: str) -> list[str]:
    path = Path(value)
    if not path.exists():
        return [f"Missing resume file: {value}"]
    locator = page.locator(f'[id="{key}"]') if key else page.locator("input[type='file']")
    if key and locator.count() == 0:
        locator = page.locator("input[type='file']")
    try:
        locator.first.set_input_files(str(path))
    except Exception as exc:
        return [f"{label}: {exc}"]
    return []


def _fill_one(page, field: dict, value: str) -> None:
    label = str(field.get("label") or "")
    locator = _locate(page, str(field.get("key") or ""), label)
    if locator is None:
        raise LookupError(f"{label} is not on the form")
    field_type = field.get("type") or "text"
    if field_type == "boolean":
        box = page.get_by_role("checkbox", name=re.compile(re.escape(label[:80]), re.I)).first
        if value.lower() in {"yes", "true", "1"}:
            box.check()
        return
    if field_type in {"select", "multi"} or locator.get_attribute("role") == "combobox":
        _choose(page, locator, value)
        return
    _type_into(locator, value)


def _locate(page, key: str, label: str):
    if key:
        by_id = page.locator(f'[id="{key}"]')
        if by_id.count():
            return by_id.first
    for alias in _aliases(label):
        exact = page.get_by_label(alias, exact=True)
        if exact.count():
            return exact.first
    for alias in _aliases(label):
        fuzzy = page.get_by_label(alias, exact=False)
        if fuzzy.count():
            return fuzzy.first
    return None


def _aliases(label: str) -> list[str]:
    aliases = [label.strip()]
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label).strip()
    if spaced and spaced not in aliases:
        aliases.append(spaced)
    if "veteran" in label.lower() and "Veteran Status" not in aliases:
        aliases.append("Veteran Status")
    return aliases


def _type_into(locator, value: str) -> None:
    locator.click()
    locator.press_sequentially(value, delay=0)
    locator.blur()


def _choose(page, locator, value: str) -> None:
    tag = locator.evaluate("element => element.tagName")
    if tag == "SELECT":
        locator.select_option(label=value)
        return
    field_id = locator.get_attribute("id") or ""
    control = page.locator(f".select__control:has(#{field_id})") if field_id else None
    if control is not None and control.count():
        control.click()
    else:
        locator.click()
    try:
        locator.press_sequentially(value, delay=0)
    except Exception:
        pass
    list_id = locator.get_attribute("aria-controls") or ""
    options = page.locator(f'[id="{list_id}"]') if list_id else page.locator("[role='listbox']")
    option = options.get_by_role("option", name=value, exact=False)
    try:
        option.first.wait_for(state="visible", timeout=2000)
        option.first.click()
        page.keyboard.press("Escape")
    except Exception as exc:
        page.keyboard.press("Escape")
        raise LookupError(f"no option matched {value}") from exc


def spawn_fill(application_id: int) -> None:
    log_path = data_dir() / "fill.log"
    handle = open(log_path, "a", encoding="utf-8")
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, "-m", "app.apply.fill", str(application_id)],
        cwd=str(Path(__file__).resolve().parents[2]),
        stdout=handle,
        stderr=handle,
        stdin=subprocess.DEVNULL,
        **kwargs,
    )


def fill_application(application_id: int) -> None:
    logging.basicConfig(filename=data_dir() / "fill.log", level=logging.INFO, encoding="utf-8")
    conn = connect()
    row = get_application(conn, application_id)
    if row is None:
        raise SystemExit(f"No application {application_id}")
    fields = json.loads(row["fields_json"])
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(data_dir() / "browser"),
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(row["url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_selector("input, textarea, select", timeout=20000)
        notes = fill_fields(page, fields)
        message = "Filled. Submit it yourself in the browser window."
        if notes:
            message = message + " " + " ".join(notes[:8])
        conn.execute(
            "UPDATE jobs SET status = 'opened', note = ?, updated_at = ? WHERE id = ?",
            (message[:1000], now(), row["job_id"]),
        )
        conn.execute(
            "UPDATE applications SET status = 'opened', updated_at = ? WHERE id = ?",
            (now(), application_id),
        )
        conn.commit()
        log.info("application %s filled; waiting for the window to close", application_id)
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            log.exception("browser closed")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.apply.fill APPLICATION_ID")
    fill_application(int(sys.argv[1]))


if __name__ == "__main__":
    main()
