from pathlib import Path

import pytest

from app.apply.fill import fill_fields

FORM = Path(__file__).parent / "fixtures" / "form.html"


def test_fill_populates_fields_and_does_not_submit():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    fields = [
        {"label": "First Name", "type": "text", "value": "Alex"},
        {"label": "Will you require sponsorship?", "type": "select", "value": "No"},
    ]
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium is not installed: {exc}")
        page = browser.new_page()
        page.goto(FORM.resolve().as_uri())
        notes = fill_fields(page, fields)
        assert notes == []
        assert page.locator("#first").input_value() == "Alex"
        assert page.locator("#sponsor").input_value() == "no"
        assert not page.url.endswith("done.html")
        assert page.get_by_role("button", name="Submit application").count() == 1
        browser.close()


def test_combobox_uses_field_id_and_skips_missing_controls():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    form = Path(__file__).parent / "fixtures" / "combobox.html"
    fields = [
        {"key": "first_name", "label": "First Name", "type": "text", "value": "Alex"},
        {
            "key": "veteran_status",
            "label": "VeteranStatus",
            "type": "select",
            "value": "I don't wish to answer",
        },
        {"key": "race", "label": "Race", "type": "select", "value": "Decline To Self Identify"},
    ]
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium is not installed: {exc}")
        page = browser.new_page()
        page.goto(form.resolve().as_uri())
        notes = fill_fields(page, fields)
        assert page.locator("#first_name").input_value() == "Alex"
        assert page.locator("#veteran_status").input_value() == "I don't wish to answer"
        assert any("Race is not on the form" in note for note in notes)
        assert not page.url.endswith("done.html")
        assert page.get_by_role("button", name="Submit application").count() == 1
        browser.close()
