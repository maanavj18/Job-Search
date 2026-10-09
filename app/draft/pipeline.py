from __future__ import annotations

import httpx

from app.draft.profile_map import draft_fields
from app.draft.questions import greenhouse_fields, standard_fields
from app.ingest.classify import choose_application, classify_url, only_simplify
from app.ingest.filters import skip_reason
from app.ingest.readme import Role, canonical_url, parse_readme

EXTRACT_JS = r"""
() => {
  function labelFor(el) {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab && lab.innerText.trim()) return lab.innerText.trim();
    }
    const wrap = el.closest("label");
    if (wrap && wrap.innerText.trim()) return wrap.innerText.trim();
    const legend = el.closest("fieldset")?.querySelector("legend");
    if (legend && legend.innerText.trim()) return legend.innerText.trim();
    return (el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || "").trim();
  }
  const fields = [];
  const seen = new Set();
  const radios = new Map();
  const push = (field) => {
    const marker = (field.key || "") + "|" + field.label;
    if (!field.label || seen.has(marker)) return;
    seen.add(marker);
    fields.push(field);
  };
  for (const el of document.querySelectorAll("input, textarea, select")) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (["hidden", "submit", "button", "reset", "image", "password"].includes(type)) continue;
    const label = labelFor(el).replace(/\s+/g, " ").slice(0, 300);
    if (type === "radio") {
      const name = el.name || label;
      if (!radios.has(name)) {
        radios.set(name, {key: name, label, type: "select", required: !!el.required, options: []});
      }
      const group = radios.get(name);
      const legend = el.closest("fieldset")?.querySelector("legend")?.innerText?.trim();
      if (legend) group.label = legend.replace(/\s+/g, " ").slice(0, 300);
      const choice = (el.closest("label")?.innerText || el.value || "").trim();
      if (choice) group.options.push({value: el.value || choice, label: choice});
      continue;
    }
    let fieldType = "text";
    let options = [];
    if (el.tagName === "TEXTAREA") fieldType = "textarea";
    else if (el.tagName === "SELECT") {
      fieldType = el.multiple ? "multi" : "select";
      options = [...el.options].filter((option) => option.value).map((option) => ({
        value: option.value,
        label: option.label,
      }));
    } else if (type === "file") fieldType = "file";
    else if (type === "checkbox") fieldType = "boolean";
    push({
      key: el.name || el.id || label,
      label,
      type: fieldType,
      required: !!el.required,
      options,
    });
  }
  for (const group of radios.values()) push(group);
  return fields;
}
"""


def load_questions(job: dict, client: httpx.Client) -> tuple[list[dict], str]:
    if job.get("ats") == "greenhouse" and job.get("ats_token") and job.get("ats_job_id"):
        response = client.get(
            f"https://boards-api.greenhouse.io/v1/boards/{job['ats_token']}/jobs/{job['ats_job_id']}",
            params={"questions": "true"},
            timeout=30,
        )
        response.raise_for_status()
        return greenhouse_fields(response.json()), ""
    return standard_fields(), "Custom questions were not in the public posting. They appear when you open the form."


def extract_forms(urls: list[str]) -> dict[str, list[dict] | str]:
    if not urls:
        return {}
    from playwright.sync_api import sync_playwright

    found: dict[str, list[dict] | str] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        for url in urls:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(1000)
                raw = page.evaluate(EXTRACT_JS)
                fields = [_from_extracted(item) for item in raw if item.get("label")]
                found[url] = fields or "The page did not expose any fields."
            except Exception as exc:
                found[url] = str(exc)
        browser.close()
    return found


def _from_extracted(item: dict) -> dict:
    return {
        "key": item.get("key") or item.get("label"),
        "label": item.get("label") or "",
        "type": item.get("type") or "text",
        "required": bool(item.get("required")),
        "options": item.get("options") or [],
        "value": "",
        "source": "blank",
        "confidence": "blank",
        "notes": "",
        "skip_llm": False,
    }


def run_pipeline(
    *,
    conn,
    sources: list[dict],
    filters: dict,
    profile: dict,
    answers: list[dict],
    client: httpx.Client,
    limit: int = 0,
    extract: bool = True,
    fetch_text=None,
    log=print,
) -> dict:
    from app.db import mark_failed, save_application, upsert_job

    parsed = 0
    browser_jobs: list[tuple[int, str]] = []
    greenhouse_jobs: list[int] = []
    for source in sources:
        text = fetch_text(source["url"]) if fetch_text else client.get(source["url"], timeout=60).text
        roles = parse_readme(text)
        parsed += len(roles)
        log(f"Read {len(roles)} roles from {source['name']}")
        for role in roles:
            queued = _store_role(conn, role, source["name"], profile, filters, client, upsert_job)
            if not queued:
                continue
            job_id, ats, url = queued
            if ats in {"lever", "ashby"}:
                browser_jobs.append((job_id, url))
            elif ats == "greenhouse":
                greenhouse_jobs.append(job_id)

    drafts: list[dict] = []
    failed = 0
    budget = limit if limit else None

    def room() -> bool:
        return budget is None or len(drafts) + failed < budget

    if browser_jobs and room():
        targets = browser_jobs if budget is None else browser_jobs[:budget]
        extracted: dict[str, list[dict] | str] = {}
        if extract:
            try:
                extracted = extract_forms([url for _, url in targets])
            except Exception as exc:
                log(f"Browser question scan unavailable ({exc}). Using standard fields.")
                extracted = {url: str(exc) for _, url in targets}
        for job_id, url in targets:
            if not room():
                break
            payload = extracted.get(url)
            if isinstance(payload, list) and payload:
                fields, note = payload, ""
            else:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                fields, note = load_questions(dict(row), client)
                if isinstance(payload, str):
                    note = payload
            _draft(conn, job_id, fields, profile, answers, save_application, drafts, note, log)

    for job_id in greenhouse_jobs:
        if not room():
            break
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or row["status"] != "new":
            continue
        try:
            fields, note = load_questions(dict(row), client)
            _draft(conn, job_id, fields, profile, answers, save_application, drafts, note, log)
        except Exception as exc:
            mark_failed(conn, job_id, str(exc))
            conn.commit()
            failed += 1
            log(f"Failed {row['company']}: {exc}")

    return {"parsed": parsed, "drafted": len(drafts), "failed": failed, "new_drafts": drafts}


def _draft(conn, job_id, fields, profile, answers, save_application, drafts, note, log) -> None:
    row = conn.execute("SELECT company, title, location, url FROM jobs WHERE id = ?", (job_id,)).fetchone()
    log(f"Drafting {row['company']} — {row['title']}")
    draft_fields(fields, profile, answers)
    save_application(conn, job_id, fields, "needs_review")
    if note:
        conn.execute("UPDATE jobs SET note = ? WHERE id = ?", (note[:1000], job_id))
    conn.commit()
    drafts.append(dict(row))


def _store_role(conn, role: Role, source: str, profile: dict, filters: dict, client, upsert_job):
    url, ats, token, job_id = choose_application(role.urls)
    reason = skip_reason(role, profile, filters)
    if reason is None and only_simplify(role.urls, ats):
        try:
            resolved = str(client.get(url, follow_redirects=True, timeout=20).url)
            ats, token, job_id = classify_url(resolved)
            url = resolved
        except httpx.HTTPError:
            pass
    if reason is None:
        reason = skip_reason(role, profile, filters)
    if reason:
        status = "skipped"
    elif ats == "manual":
        status = "manual"
    else:
        status = "new"
    record = {
        "dedupe_key": canonical_url(url) or f"{role.company}|{role.title}|{role.location}",
        "source": source,
        "section": role.section,
        "company": role.company,
        "title": role.title,
        "location": role.location,
        "url": url,
        "urls": role.urls,
        "ats": ats,
        "ats_token": token,
        "ats_job_id": job_id,
        "age_text": role.age_text,
        "age_days": role.age_days,
        "flags": role.flags,
        "status": status,
        "skip_reason": reason,
    }
    upsert_job(conn, record)
    conn.commit()
    if status != "new":
        return None
    row = conn.execute("SELECT id, status FROM jobs WHERE dedupe_key = ?", (record["dedupe_key"],)).fetchone()
    if row is None or row["status"] != "new":
        return None
    existing = conn.execute("SELECT 1 FROM applications WHERE job_id = ?", (row["id"],)).fetchone()
    if existing:
        return None
    return int(row["id"]), ats, url
