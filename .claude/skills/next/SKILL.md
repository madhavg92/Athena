---
name: next
description: Continue building Athena. Use when the user says next, continue or resume, or at the start of a build session.
---

# Continue the Athena build

Repeat these steps until a stop condition happens.

1. Read `docs/PROGRESS.md` and `docs/BLOCKERS.md`. Read the section of `docs/BUILD_PLAN.md` for the current milestone.
2. Select the first unchecked task.
   - If the task needs a closed gate: do its fixture part only, write tests for it, and add a note to the task in PROGRESS ("fixture done; live waits for Gx"). Tick it only if the task has no live part left. Go to the next task.
3. Do the task:
   1. Write the plan in not more than 3 lines.
   2. Write or extend the tests first.
   3. Write the code.
   4. Run `pytest -q` and `ruff check .`. Fix until both are clean.
4. Tick the task in `docs/PROGRESS.md`, add a one-line note to the Log, and commit: `git add -A && git commit -m "<task id>: <summary>"`.
5. Go back to step 1. Do not ask the user between tasks.

## Stop conditions

Stop and report when one of these happens:
- The end of release 1 (all M1–M5 tasks done or waiting for a gate).
- The end of release 2 (all M6–M9 tasks done or waiting for a gate).
- All remaining tasks wait for a gate.
- A hard rule in CLAUDE.md would be broken.
- A choice cannot be reversed or would change docs/SPEC.md. Record it under "Open" in DECISIONS and ask.
- The same failure stays after 3 different fix attempts. Record it under "Stuck items" in BLOCKERS with the error and what you tried. Continue with the next task that does not depend on it. If there is none, stop.

## Report when you stop

Keep it short:
1. **Done:** task IDs and one line each.
2. **Waiting for you:** each gate that blocks the next task, and exactly what to give (no secrets in chat; secrets go in `.env`).
3. **Stuck:** items, if any.
4. **Next:** the task that runs when the user types `/next`.
5. **Try it:** 2–3 commands that the user can run now (fixture mode).
