# Findings

The critic appends findings here. Evidence must be reproducible. No names, emails, phone numbers, resume text, or answer text.

## Review rotation

- [x] Outcome: did the last run produce drafts the user can review?
- [x] Answer safety: profile matching, answer bank, model fill
- [ ] Ingest: README parsing, sections, closed flags, dedupe
- [ ] Classification and coverage: ATS URL shapes, manual share
- [ ] Drafting pipeline: ordering, persistence, resumability
- [ ] Review UI: saving, answer bank writes, status changes
- [ ] Fill: browser filling, never submitting, concurrent opens
- [ ] Self-improvement: `learn`, hooks, lessons
- [ ] Tests: fixture realism, missing regression cases
- [ ] Docs and skills: README, AGENTS.md, skill accuracy

## Open

| ID | Sev | Area | Finding | Evidence | Status |
|----|-----|------|---------|----------|--------|
| C02 | P0 | outcome | The last run drafted nothing. Ingest stopped at software-engineering role 526 of 628, four other sections were never stored, and 94 supported jobs sit at `new` with no application. Offline replay ingests all 1,894 roles in 2 s, so the stall was environmental and undiagnosable because no run was logged. | `audit`: `run:stuck-new`, `run:no-record`. Run log added in this cycle; root cause still unknown until the next full run. | open |
| C03 | P0 | self-improvement | `learn` reported "None. Do not invent a code change." while zero drafts existed. It only sees failed jobs, overrides, and scan notes. `lessons.md` has no entries, so the improve loop has never completed a cycle. | `python -m app.cli learn` on the current database | open |
| C04 | P1 | answers | The answer bank labels any fuzzy match at 90 or above as `bank`/`high`, the same as an exact match. Corrections to those are never logged because `log_override` ignores `bank`. A saved "Why Anduril?" essay is offered for "Why Sigma Computing?" at 86. | `match_answer` probe; `app/learn.py` `log_override` | open |
| C05 | P1 | drafting | Every Lever and Ashby browser scan runs before any draft is saved. 51 Greenhouse jobs that need no browser wait behind up to 43 page loads, and a killed run keeps nothing. | `app/draft/pipeline.py` `run_pipeline` order | open |
| C06 | P1 | ingest | `job-boards.eu.greenhouse.io` (5 jobs) and one `boards.greenhouse.io` shape are classified manual. | `audit`: `classify:*` | open |
| C07 | P1 | review | Saving a review writes profile facts such as GPA, school, and city into `answers.yaml`. `is_identity` only covers names, contacts, and links. The answer policy says those belong in `profile.yaml`. | `app/web.py` `_apply_form`, `app/draft/bank.py` `is_identity` | open |
| C08 | P1 | answers | The model call sends the whole profile, including phone and address, for every application. The default model is `gpt-4o-mini`. Essay questions invite fabricated answers that are only marked `check`. | `app/draft/llm.py` | open |
| C09 | P2 | fill | A second "Save and open filled form" while a window is open collides on the persistent browser profile. The error only reaches `fill.log` and the page still says it is opening. | `app/apply/fill.py` `spawn_fill` | open |
| C10 | P2 | tests | Fixtures are hand-made (a 6-row README, a hand-written Greenhouse payload). No test covers an interrupted run, adversarial labels, or `learn` missing stuck jobs. | `tests/` | open |
| C11 | P2 | skills | The job-applier skill says "Do not stop after a partial ingest when the command is still making progress", which asks the agent to tolerate a slow, non-incremental run instead of fixing it. | `.cursor/skills/job-applier/SKILL.md` | open |
| C15 | P3 | web | `app = create_app()` at import time creates the data directory as a side effect. Connections are opened per request and never closed. | `app/web.py` | open |
| C16 | P3 | answers | EEO detection uses substrings, so "trace" matches "race". The field is blanked, so it is noise, not a wrong answer. | `app/draft/profile_map.py` `_eeo_answer` | open |

## Needs the user

| ID | Sev | Finding | What is needed |
|----|-----|---------|----------------|
| C12 | P1 | `profile/profile.yaml`, a resume, and `.env` do not exist. Every draft would be for the example person. The career-profile skill points to a `profile.md` that does not exist either. | Copy `profile/profile.example.yaml` to `profile/profile.yaml` and fill it, set `resume_path`. |
| C13 | P2 | 379 of 507 stored jobs are manual, mostly Workday. The app covers about a fifth of listings. SmartRecruiters (10) and Rippling (7) have public posting pages. | Decide whether to add a board. |

## Fixed

| ID | Finding | Fix |
|----|---------|-----|
| C14 | No version control and no `AGENTS.md` for a loop that edits its own code. | `git init`, baseline `4c81b83`; `AGENTS.md` added |
| C01 | Substring profile matching filled question-shaped labels with unrelated facts at `high` confidence (11 of 11 audit labels). | Facts need a whole-word keyword, no yes/no or essay prefix, and a short label or "your X". Sponsorship and authorization only answer the standard yes/no form. `test_question_labels_never_get_unrelated_profile_facts` |

## Log

- 2026-10-09 Initial critique. Added `audit`, run log, critic skill, ledger, `AGENTS.md`, git baseline.
- 2026-10-09 C01 fixed. Audit `misfill:*` went from 11 to 0, positive controls still fill.
