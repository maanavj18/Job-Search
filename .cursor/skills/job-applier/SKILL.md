---
name: job-applier
description: >-
  Finds Summer 2027 internships from the Pitt CSC / Simplify README, drafts
  Greenhouse, Lever, and Ashby applications, and opens a filled form for
  review. Use when the user asks to find internships, draft an application,
  refresh the review queue, improve this job applier, or change how it works.
---

# Job applier

Run the local app. Do not apply on the user's behalf.

## Commands

From the repo root:

```bash
python -m app.cli run
python -m app.cli serve
python -m app.cli learn
```

`run` fetches the configured README, drafts every new Greenhouse, Lever, and Ashby match, and stops at the review queue. Report the queue counts when it finishes. Do not stop after a partial ingest when the command is still making progress. Then run `learn`. If it lists open items, follow Improve itself.

`serve` opens http://127.0.0.1:8000. The user edits drafts there.

`learn` prints misses worth a code change. It does not print answer text.

## Hard rules

- Never invent a biography fact. If it is not in `profile/profile.yaml` or `profile/answers.yaml`, leave the field blank.
- Never commit `profile/profile.yaml`, `profile/answers.yaml`, `.env`, or a resume.
- Never click Submit, never solve a captcha, and never store a site password.
- Demographic questions stay "decline" unless the profile sets something else.
- A blank answer is a successful result when the fact is missing.

## Improve itself

The loop is on while `.cursor/improve.enabled` exists. Delete that file to stop it. Each cycle fixes one open item, then the stop hook continues only if `.cursor/learn-next.json` says so, at most five times.

1. Run `python -m app.cli learn` and use the open items. Missing required facts stay blank.
2. If there is no open item, write `.cursor/learn-next.json` as `{"continue": false}` and stop.
3. Take the first open item. Change the smallest piece of code or skill text that prevents that class of miss. Add a regression test with fake data.
4. A removed posting or a missing biography fact is not a code change. Append a lesson that includes the item id and says no code change, then go back to step 1.
5. For a check-flagged answer, make the match exact or reject it. Do not auto-accept a weaker match.
6. Run `python -m pytest`.
7. Append a lesson to [lessons.md](lessons.md) with the item id, the signal, the change, and the test. No personal facts.
8. Run `learn` again. If an open item remains, write `{"continue": true, "item": "<id> <one sentence>"}`. Otherwise write `{"continue": false}`.

## Where the logic lives

- Sources and section filters: `config/sources.yaml`, `config/filters.yaml`
- Facts: `profile/profile.yaml` (copy from `profile/profile.example.yaml`)
- Saved repeating answers: `profile/answers.yaml`
- ATS URL shapes and question endpoints: [ats.md](ats.md)
- What may be answered automatically: [answer-policy.md](answer-policy.md)
- What the loop has already learned: [lessons.md](lessons.md)

Database and the browser profile are under `%LOCALAPPDATA%\JobSearch`, not in this OneDrive repo.
