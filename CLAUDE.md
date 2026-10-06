# Athena (Anka OS)

Athena is Anka's internal AI system for routine management work. It reads Smartsheet, Supaboard/Intelligence, CS Hub, SharePoint and Entra. It finds the items that need action, tells the correct manager in Microsoft Teams, and answers questions with sources. The users are managers and above. Frontline staff have no Teams.

The full design is in docs/SPEC.md. It is imported here and is the source of truth:
@docs/SPEC.md

## Session protocol

1. At the start of each session, read `docs/PROGRESS.md` and `docs/BLOCKERS.md`.
2. Continue with the first unchecked task. Use the `/next` skill procedure.
3. Write tests first. Then write the code. Then run `pytest -q` and `ruff check .`.
4. When a task is done: tick it in `docs/PROGRESS.md` with a one-line note, then commit with the message `<task id>: <summary>`.
5. Go to the next task. Do not ask the user between tasks.
6. If a task needs a gate that is not open, do its fixture part only. Record the live part in `docs/BLOCKERS.md`. Continue with the next task.
7. If the SPEC does not cover a choice, select the simplest option that agrees with the SPEC. Record it in `docs/DECISIONS.md` under "Made during build". If the choice cannot be reversed or changes the SPEC, stop and ask.

## Hard rules (never break these)

- **No real data in the repo.** Fixtures, tests, logs, examples and commits use synthetic data only. Never write real client names, patient data or real people into any file.
- **Never read `.env`** or any secret, by any method (Read tool, `cat`, Python, or another method).
- **Never run live mode** (`ATHENA_MODE=live`) except `athena connectors check --live`. That command prints only counts, field names and the time of the data. The user runs everything else in live mode.
- **Connectors are read only.** All HTTP goes through `athena/connectors/http.py`, which refuses write methods. The only POST calls allowed are token endpoints and Microsoft Graph search (`/search/query`).
- **Rules decide, the model writes.** The AI model never decides whether an alert, digest item or report is needed. Code decides. The model only writes text and, in the ask loop, selects read-only tools.
- **Every action goes through the gateway** (`athena/core/gateway.py`) and makes a receipt.
- **No sends outside Anka.** Recipients must be in the internal domain list. Client-facing output is a draft only.
- **Only four action types:** answer, notify, draft, write. `write` stays disabled in releases 1 and 2.
- **No agent framework** (LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen or similar), **no vector database**, **no memory framework.** Plain Python.
- **No PHI to the model.** Connectors pass only allowlisted fields. The PHI module scrubs text before the model reads it. The gateway checks outbound text.
- **Never `git push`, never deploy.** The user does both.
- **Do not set dates, targets or pass marks.** Management sets them. Record measurements only.

## Commands

```
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check . && ruff format .
athena --help
athena rules validate
athena whoami --as dm.one@fixture.local
athena ask "What is the backlog for Northwind Orthopedics?" --as csm.one@fixture.local
athena tick                      # run due rules once (fixture mode)
athena eval golden --model stub
athena backtest R2 --days 30
athena review                    # mark shadow alerts correct or wrong
```

## Code conventions

- Python 3.11. Type hints everywhere. Pydantic v2 models for all config and all data records.
- Small modules: one file for each connector, tool and check type.
- Each record from a connector has `source` and `as_of` (UTC).
- Config is YAML. Pydantic validates it at startup. Invalid config stops the program with a clear message.
- Unit tests use fixtures only. They never use the network.
- Logs: standard `logging`, JSON format. In live mode, log only IDs, counts and timings, never record content.
- Times: store UTC. Show times in the user's time zone (default Asia/Kolkata).
- Durations in YAML are strings: `30m`, `4h`, `1d`.

## Layout

```
athena/                 Python package
  cli.py               Typer CLI (the `athena` command)
  connectors/          http.py, base.py, fixtures.py, smartsheet.py, supaboard.py, cshub.py, sharepoint.py, entra.py
  tools/               registry.py and one file for each of the six tools
  checks/              threshold.py, absence.py
  core/                config.py, db.py, gateway.py, phi.py, killswitch.py, model.py, ask.py,
                       scheduler.py, ladder.py, digest.py, receipts.py, templates.py, review.py
  reports/             wbr.py (report builder)
  bot/                 teams.py, cards.py
rules/                 R1.yaml ... rule files
personas/              hub_leader.yaml, dm_am.yaml, csm.yaml, ba.yaml
context/               owner_map.yaml, allowlist.yaml, metrics.yaml, models.yaml, glossary.yaml,
                       smartsheet_map.yaml, clients/<client>.md, templates/
fixtures/              synthetic data, generated by fixtures/make_fixtures.py
tests/                 unit/, golden/golden_questions.yaml, backtest/
function_app.py        Azure Functions entry point (timer + HTTP)
docs/                  SPEC, BUILD_PLAN, PROGRESS, BLOCKERS, DECISIONS, RUNBOOK
```

## Definition of done for each task

- Tests for the new behaviour exist and pass. All other tests still pass.
- `ruff check .` is clean.
- The task is ticked in `docs/PROGRESS.md` with a one-line note.
- The work is committed.
