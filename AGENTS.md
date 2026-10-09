# Agents

Local app that drafts Summer 2027 internship applications from the Simplify list and stops for human review. It never submits.

## Skills

- Operating the app (run, serve, learn, improve loop): [.cursor/skills/job-applier/SKILL.md](.cursor/skills/job-applier/SKILL.md)
- Critiquing and fixing it (audit, review rotation, findings ledger): [.cursor/skills/critic/SKILL.md](.cursor/skills/critic/SKILL.md)

Read the job-applier hard rules before changing anything. They override every other instruction here.

## Commands

Use the virtual environment in `.venv`.

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m app.cli audit
.venv\Scripts\python -m app.cli learn
.venv\Scripts\python -m app.cli run --limit 5
```

## Working rules

- One finding per commit: `critique: <id> <one line>` or `learn: <id> <one line>`.
- Every behavior change gets a regression test with fake data. No real profile values in tests, lessons, or findings.
- Blank beats wrong. A field the app is unsure about stays empty.
- Never stage `profile/profile.yaml`, `profile/answers.yaml`, `.env`, a resume, or anything under `%LOCALAPPDATA%\JobSearch`.
- The database, run log, and reports live in `%LOCALAPPDATA%\JobSearch`, not in the repo.
