---
name: critic
description: >-
  Runs the critique loop for the job applier: audits outcomes against ground
  truth, reviews one area adversarially, records findings with evidence, and
  fixes the worst agent-fixable finding with a regression test. Use when the
  user asks to critique, audit, review progress, or run the critique loop.
---

# Critic

Assume the app is broken until a command proves otherwise. Passing tests and a clean `learn` report are not evidence that it works. The question every cycle answers is: would the user get correct, submittable drafts today?

The [job-applier skill](../job-applier/SKILL.md) hard rules still apply. The critic never invents a biography fact, never submits, and never edits `profile/profile.yaml` or `profile/answers.yaml`.

## One cycle

1. Gather evidence. Run all three and read the output:
   ```bash
   python -m app.cli audit
   python -m app.cli learn
   python -m pytest -q
   ```
2. Review one area. Take the next unchecked area in the rotation in [findings.md](findings.md). Read its code and run at least one probe against real data or a fake input that tries to break it. A finding needs evidence: a command, its output, or a failing test. Opinions without a reproduction go in the ledger as P3 at most.
3. Record. Add each new finding to [findings.md](findings.md) with the next `C` id, severity, area, evidence, and status `open`. Tick the area in the rotation. When every area is ticked, clear the ticks.
4. Pick. Take the worst open finding that does not need the user. Audit P0 findings come before ledger P0 findings at the same severity.
5. Fix. Change the smallest piece of code or skill text that removes the class of problem, not just the one example. Add a regression test with fake data. If the audit detects it, the audit corpus or check must keep detecting it.
6. Verify. Run `python -m pytest -q` and `python -m app.cli audit`. The finding must be gone and nothing new may appear. If the fix fails twice, revert it with git, mark the finding `blocked` with the reason, and pick the next one.
7. Commit. `git add -A` then `git commit -m "critique: <id> <one line>"`. Check that `git status` shows no profile, answers, `.env`, or resume file staged.
8. Close. Set the finding to `fixed <short hash>` and append one line to the log at the bottom of [findings.md](findings.md).
9. Hand off. Write `.cursor/critique-next.json` as `{"continue": true, "item": "<id> <one sentence>"}` when an agent-fixable P0 or P1 remains, otherwise `{"continue": false}`.

Do up to three fixes per wake. Stop early when a fix needs a decision.

## Severity

- P0: the user could submit a wrong answer, or the app silently produces nothing.
- P1: a whole class of jobs or answers is lost, hidden, or unreviewable.
- P2: wasted effort, fragile behavior, or a gap that will become P1 at scale.
- P3: style, naming, or a suspicion without a reproduction.

## Needs the user

Missing profile facts, a resume, API keys, and adding a new job board are the user's call. List them under "Needs the user" in the ledger and in the reply. Do not work around them, and do not stop the loop for them.

## What does not count as a fix

- Lowering a threshold, deleting an assertion, or adding a skip to make a check pass.
- Marking a wrong answer `check` instead of not filling it. Blank is the safe result.
- Prompt text in a skill that asks the agent to tolerate a code defect.
- Suppressing an audit check. A finding only closes when the audit stops reporting it for the right reason.
