# Job Search

A local app that watches the [Pitt CSC / Simplify Summer 2027 internship list](https://github.com/SimplifyJobs/Summer2027-Internships), drafts Greenhouse, Lever, and Ashby applications from your profile, and stops so you can review and submit.

It does not click Submit.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m playwright install chromium
copy profile\profile.example.yaml profile\profile.yaml
copy .env.example .env
```

Edit `profile\profile.yaml` with your own facts and set `resume_path` to your resume file. Optional: put an OpenAI-compatible API key and SMTP settings in `.env`. Without an API key, unknown questions stay blank. Without SMTP, the review page is the notification.

`config\filters.yaml` starts with software engineering roles. Add `data-science` to include those listings too.

The database and browser profile are stored in `%LOCALAPPDATA%\JobSearch` so OneDrive does not lock them.

## Daily use

```powershell
.venv\Scripts\python -m app.cli run
.venv\Scripts\python -m app.cli serve
```

`run` fetches new roles and drafts every matching application. Open http://127.0.0.1:8000, check each draft, then choose **Save and open filled form**. Submit on the company site yourself, and come back to mark it submitted.

Your corrections to custom questions are saved in `profile\answers.yaml` and reused next time. Replacing a fuzzy or model draft also records the question, without the answer text, so the agent can tighten that match later.

```powershell
.venv\Scripts\python -m app.cli learn
```

`learn` lists failed fetches and overridden drafts. The agent fixes one of those at a time, with a test, and records the lesson in `.cursor\skills\job-applier\lessons.md`. It does not invent missing facts. Delete `.cursor\improve.enabled` to turn that loop off.

## Tests

```powershell
.venv\Scripts\python -m pytest
```
