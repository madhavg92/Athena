# ATHENA — bootstrap for Claude Code

**Athena** is the codename for the first build of Anka OS. Athena is the Greek goddess of wisdom and strategy, and the advisor of heroes. The name fits the Anka project names Codex, Atlas and Hermes.

This one file sets up the whole project. Claude Code reads it, writes the project files, and then builds Athena step by step. It builds against synthetic data first. It stops when it needs something that only a person can give: an API key, an admin consent, or a decision.

---

## Part 1 — For Madhav: how to start

1. Install Python 3.11 or later, Git and Claude Code.
2. Make an empty folder and start Git:
   ```
   mkdir athena && cd athena && git init
   ```
3. Copy this file into the folder.
4. Start Claude Code with this command:
   ```
   claude --permission-mode acceptEdits "Read ATHENA_BOOTSTRAP.md and follow Part 2 exactly."
   ```
5. In later sessions, open the folder and type `/next`. Type `/status` to see the progress and the items that need you.

**What you must give it later** (it lists these in `docs/BLOCKERS.md`):

| Gate | What | From |
|---|---|---|
| G1 | Smartsheet read token, sheet IDs and column names | Ops / Smartsheet admin |
| G2 | Supaboard / Intelligence API documents and a read-only key | Supaboard |
| G3 | CS Hub API read access (tickets, health) | Vishal |
| G4 | Entra app registration, Graph permissions, admin consent, SharePoint site list | IT (Shivesh) |
| G5 | Open-weight model endpoint under a contract that covers our data | Madhav |
| G6 | Teams bot registration and permission to install for pilot users | IT |
| G7 | Standard WBR template | BA team |
| G8 | "Late" and "at risk" values, work hours, digest times | Hub leader, pilot users |
| G9 | 20 real questions for each pilot persona | Pilot users |
| G10 | Real owner list: client, hub, hub leader, DM/AM, CSM, BA | Ops |
| GD | Azure subscription and resource group. You run the deploy. | IT |

**Safety for you:** put secrets only in `.env`. Claude Code is told never to read it. Do not put real client or patient data in the repo. Claude Code must not run "live" commands that print real records. You run live mode yourself.

---

## Part 2 — For Claude Code: what to do

You are setting up and then building **Athena**. Do these phases in order.

### Phase A — Write the project files

This file contains the project files below. Each file starts with a line `=== FILE: <path> ===` and ends with a line `=== END FILE ===`. Write the content between those two lines to the path, exactly as written. Do not change the content. Do not add other files in this phase.

### Phase B — First commit

1. Make a Python virtual environment: `python3 -m venv .venv`.
2. Run `git add -A && git commit -m "M0: scaffold from ATHENA_BOOTSTRAP.md"`.
3. Keep `ATHENA_BOOTSTRAP.md` in the root as the record of the seed. Do not run Phase A again in later sessions.

### Phase C — Start the build

Follow `.claude/skills/next/SKILL.md`. Work through `docs/PROGRESS.md` task by task. Do not ask the user between tasks. Stop only at a stop condition in that skill. When you stop, give the report that the skill describes.

---

## Part 3 — Project files

=== FILE: CLAUDE.md ===
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
=== END FILE ===

=== FILE: docs/SPEC.md ===
# Athena — design specification

## 1. Scope

Athena does routine management work: watch, chase, answer and report. It is one platform. A new job is a new rule file, not new code.

**In scope for this build:** release 1 (search and answer) and release 2 (alerts, digests, report drafts) for four pilot personas: hub leader, DM/AM, CSM and BA.

**Not in scope:**
- RCM work automation (EV, AR, PP). The workflow tools own that work.
- Sending anything to clients.
- Changing data in any source system.
- Reading email content or Teams chat content.
- Later releases: people table, dates register, Extract (transcripts), Triage (Jev). These need management decisions first.

Athena is the **only** system that sends management alerts. CS Hub and the workflow tools give data. Athena sends the alerts.

## 2. Architecture

```
Sources (Smartsheet, Supaboard, CS Hub, SharePoint, Entra, Git context files)
   -> Connectors (read only, add source + as_of, allowlisted fields, PHI scrub)
   -> Rule loop (scheduler -> check -> alert state -> ladder)   |   Ask loop (model + read-only tools)
   -> AI model (writes text only; swappable)
   -> Gateway (all checks, then the action, then a receipt)
   -> Outputs: Teams (answers, alerts, digests), drafts folder / SharePoint (drafts), receipts DB
```

Three parts:
- **Brain:** the data and context that the model reads (section 3).
- **Loops:** the rule loop and the ask loop (sections 4 and 5).
- **Harness:** tests and controls: golden questions, backtests, shadow mode, gateway, kill switches, receipts (sections 6 and 12).

## 3. Brain

| Layer | Holds | Where | How read |
|---|---|---|---|
| Live data | Tasks, metrics, tickets, people | Smartsheet, Supaboard, CS Hub, Entra | Connectors, live queries, no copies |
| Documents | SOPs, contracts, client documents | SharePoint, allowlisted sites only | Microsoft Graph search |
| Context files | Owner map, personas, metric definitions, glossary, client profiles | `context/`, `personas/` in Git | Read by name |
| Question log | Each question, answer and "I do not know" | Database | People read it and add missing context |

Rules:
- Do not copy documents into an index or a store. Query the sources.
- Do not use a vector database.
- Each metric that users ask about has a definition in `context/metrics.yaml`.
- Memory: each user has a persona (scope, work hours, digest time). Each conversation keeps its last 6 turns. No long-term chat memory.

## 4. Rule loop

1. The scheduler runs every 15 minutes (`athena tick` locally; an Azure Functions timer in production).
2. For each rule whose cron schedule is due, the rule loop:
   1. Reads the source through its connector.
   2. Checks data freshness. If the newest `as_of` is older than `data_max_age`, it logs "stale", makes no new alerts, and marks the rule stale for digests.
   3. Runs the check (code, not AI). The check returns hits: `{key, severity, client, fields}`.
   4. For each hit, it opens or updates an alert (key = rule_id + item key).
   5. For each open alert whose condition is now clear, it closes the alert.
3. The ladder decides who gets each open alert and when:
   - Each ladder step has `after` (time since the alert opened) and `to` (an owner-map role).
   - Within a step, the person gets at most 2 messages: the first message, then one reminder after `renudge_after`. Then the alert goes to the next step.
   - The gateway also enforces the limit of 2 messages for each alert and each person.
4. `delivery: now` sends at once (inside work hours). `delivery: digest` adds the item to the person's next digest.
5. Message text: code builds a structured payload (client, item, due, age, severity). The model writes a short message from that payload only. If the model fails, a plain template is used.
6. Mode `shadow`: alerts go to the review list, not to people. Owners mark each alert correct or wrong (`athena review`, and Teams card buttons later).

### Check types

**threshold:** runs a list of conditions on each record. All conditions in a list must be true. Severities are checked in the order written. The first match wins.

Condition = `{field, op, value}`. Ops:
- `eq`, `ne`, `lt`, `lte`, `gt`, `gte` — compare with a value
- `lt_field`, `gt_field` — compare with another field of the same record (value = field name)
- `before`, `after` — datetime compared with a value (`now` is allowed)
- `within` — datetime is between now and now + duration
- `older_than` — datetime is earlier than now − duration
- `is_null`, `not_null`

**absence:** finds expected items that did not arrive. Params: `expected` (list or calendar: cron + key), `arrived_source`, `match_key`, `grace` (duration).

No `eval`. No expression strings. Add a new op only in `checks/threshold.py` with tests.

## 5. Ask loop

1. A user asks a question (Teams, or `athena ask` locally).
2. The gateway checks the kill switch and finds the user's persona and scope.
3. If the question starts with "brief" or "brief me", use the R4 template. Otherwise use R1.
4. The model gets: a system prompt (rules below), the persona, the client names in scope, the relevant metric definitions, the last 6 turns, and the tool definitions.
5. The model can make up to 8 tool calls. Each call goes through the gateway (scope check), then the tool.
6. The final answer = the model's text + a "Sources" footer. **Code makes the footer** from the tool calls that returned data: source name, link if any, as_of.
7. Validation: if the answer has facts but no tool returned data, replace it with "I do not know" and the list of what was checked.
8. Log the question, answer, tools used, latency and tokens to the question log and a receipt.

System prompt rules for the model:
- Use only tool results and context files. Do not use outside knowledge about clients.
- If the tools do not give the answer, say "I do not know" and say what you checked.
- If a tool result is older than the rule's `data_max_age`, say "Data is not current" and give the as_of time.
- Never give patient-level details.
- Keep answers short: the answer first, then up to 5 bullet points.

## 6. Gateway

Every action is an `Action`:
```
Action(type: answer|notify|draft|write, rule_id, actor, recipients[], clients[], text,
       payload, delivery: now|digest, sources[{name, ref, as_of}], phase, mode: shadow|live, item_key)
```
`gateway.submit(action)` runs these checks in this order and stops at the first failure:
1. Kill switch: global, rule, user.
2. Action type allowed: `write` is refused in this build.
3. Recipients internal: each recipient email domain is in `internal_email_domains`.
4. Scope: each client in `clients` is in the scope of each recipient (and of the actor for answers).
5. Freshness: each source `as_of` is within the rule's `data_max_age`, or the text says "Data is not current".
6. PHI lint: outbound text passes `phi.lint()`.
7. Message limit: not more than 2 notify messages for one item_key to one person.
8. Work hours: `notify` + `now` outside the recipient's hours is held until their next work start.
9. Mode: `shadow` → write to the review list, do not deliver.

Then: deliver (Teams, digest queue, or drafts folder) and write a receipt. A refusal also writes a receipt with `status: refused` and the reason.

## 7. PHI handling

- Each connector declares `ALLOWED_FIELDS`. Other fields are dropped at read time.
- `phi.scrub(text)` runs on all free text (task names, ticket subjects, document snippets) before the model reads it. It masks: SSN patterns, dates of birth near "DOB", MRN / member ID / account number patterns, phone numbers, email addresses outside the internal domains, and names after "patient" / "pt" / "member". It returns the text and a `suspect` flag.
- `phi.lint(text)` runs in the gateway on outbound text. If a pattern matches, the action is refused.
- Regex cannot find all names. This is a known limit. The real control is G5: a model host under a contract that covers the data. Record this in DECISIONS.

## 8. Action types, delivery, phases, modes

| Type | Does | This build |
|---|---|---|
| answer | Answers the person who asks | Yes |
| notify | Sends a Teams message to an Anka person | Yes; shadow for 1 week first |
| draft | Makes a document for a person to review | Yes; never sent to a client |
| write | Changes data in a system | Disabled |

- `delivery`: `now` (only for items a person must do today) or `digest` (default).
- `phase`: 1 = AI suggests, 2 = AI acts and a person checks, 3 = AI acts. In this build all rules are phase 1 or 2. Phase changes are config. Automatic demotion: if wrong alerts in the last 7 days exceed the rule's `max_wrong_rate`, set the rule to the phase below and record it.
- `mode`: `shadow` or `live`.

## 9. Data model (SQLAlchemy 2.0; SQLite locally, Postgres in production)

- `receipts`: id, time, actor, recipient, rule_id, action_type, delivery, mode, sources (JSON), output, status (shadow|sent|held|read|acted|closed|refused), reason, tokens_in, tokens_out, cost_usd, latency_ms
- `alerts`: id, rule_id, item_key, client, severity, opened_at, closed_at, ladder_step, last_sent_at (JSON by person), sends_count (JSON by person), state (open|closed), payload (JSON)
- `digest_items`: id, user, rule_id, item_key, text, created_at, sent_at
- `question_log`: id, time, user, question, answer, tools (JSON), idk (bool), stale (bool), tokens, latency_ms
- `turns`: id, conversation_id, user, role, text, time
- `kill_switches`: scope (global|rule|user), key, on (bool), set_by, set_at
- `review_marks`: alert_id, reviewer, verdict (correct|wrong), note, time

## 10. Config formats

**Rule file** (`rules/<ID>.yaml`): `id, name, trigger, source, check, data_max_age, owner, ladder, renudge_after, close_when, message, action, delivery, phase, mode, max_wrong_rate` (+ rule-specific keys). See the R1–R5 files.

`trigger` is one of:
- `{cron: "<5-field cron>", tz: "<IANA tz>"}`
- `{question: any}` (R1) or `{question: brief}` (R4)

**Persona** (`personas/<name>.yaml`): `persona, scope, rules, sources, sharepoint_sites, work_hours, digest_time, tz, must_not`.

**Owner map** (`context/owner_map.yaml`): `people` (email → name, persona, optional work_hours) and `clients` (key → name, hub, hub_leader, dm_am, csm, ba). Scope expressions in personas use the form `clients where <role> = me`.

**Allowlist** (`context/allowlist.yaml`): SharePoint sites per group, `internal_email_domains`.

**Metrics** (`context/metrics.yaml`):
```yaml
backlog:
  meaning: "<one sentence, approved by the hub leader>"
  source: supaboard.metrics
  field: backlog
  owner: <email>
```

**Models** (`context/models.yaml`):
```yaml
default: stub
models:
  stub: {kind: stub}
  candidate_a:
    kind: openai_compatible
    base_url_env: MODEL_A_BASE_URL
    api_key_env: MODEL_A_API_KEY
    model: "<model name>"
    price_per_mtok_in: 0.0
    price_per_mtok_out: 0.0
    contract_covers_data: unknown   # yes | no | unknown (G5)
```

**Smartsheet map** (`context/smartsheet_map.yaml`): sheet ID for each client and the column names for task, owner, due, status, last_update (G1).

## 11. Tools (ask loop)

All tools are read only, take the user's scope, return records with `source` and `as_of`, and pass through the gateway.

| Tool | Returns | Source |
|---|---|---|
| `get_tasks(client, status=None)` | Open tasks: id, title, owner, due, status, last_update | Smartsheet |
| `get_metrics(client, metric, period)` | Values and targets for a metric and period | Supaboard |
| `get_tickets(client, status=None)` | Tickets and the client health score | CS Hub |
| `search_documents(client, words)` | Up to 5 short snippets with links | SharePoint (allowlist) |
| `get_owner(client)` | Hub leader, DM/AM, CSM, BA | Owner map |
| `get_client_profile(client)` | The client profile file | `context/clients/` |

Each tool has a JSON schema for the model. Add a new tool only after a review by the platform owner (the user).

## 12. Harness

- **Golden questions** (`tests/golden/golden_questions.yaml`): each item has `id, persona, user, question, expect`. `expect` can have `contains` (strings), `not_contains`, `tools` (tools that must be called), `idk: true`, `refused: true` (out of scope), `stale: true`. `athena eval golden --model <name>` writes `reports/eval-<model>-<timestamp>.md` with pass rate, tool-call accuracy, average latency, tokens and estimated cost.
- **Backtest:** `athena backtest <rule> --days N` replays `fixtures/history/` (or, later, live history run by the user). It reports alerts opened, messages that would be sent per person per day, and wrong alerts where history has labels.
- **Shadow review:** `athena review` lists shadow alerts and records correct or wrong.
- **Rule check in CI:** `athena rules validate` checks every YAML file. Then a dry run of each rule on fixtures.
- **Measurement** (from receipts and logs): alerts sent, closed, wrong; time from alert to action; changes to drafts; questions answered and unanswered; model cost for each rule and each user. `athena stats` prints these.

## 13. Model layer

`athena/core/model.py` defines one interface:
```python
class ModelClient(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None) -> ModelReply: ...
# ModelReply: text, tool_calls[{name, arguments}], tokens_in, tokens_out, latency_ms
```
Implementations:
- `StubModel`: deterministic and scripted for tests. For golden questions in fixture mode it uses simple routing (client name + keywords → tool) and templated answers, so the harness can be tested without a real model.
- `OpenAICompatModel`: any OpenAI-compatible chat-completions endpoint with tool calls (vLLM, Ollama, Azure AI Foundry and others). Settings come from `context/models.yaml` and environment variables.

The model never sees secrets, raw records outside tool results, or PHI.

## 14. Teams and Azure

- One Azure Functions app (`function_app.py`, Python v2 programming model):
  - Timer trigger every 15 minutes → `scheduler.tick()`.
  - HTTP trigger `/api/messages` → Teams bot → ask loop.
- Teams: Azure Bot + Entra app registration + Microsoft 365 Agents SDK for Python. **Check the current Microsoft documentation for the package names and the sample before writing code** (learn.microsoft.com). Record the versions in DECISIONS.
- Map the Teams user to the owner map by email. If the user is not in the owner map, reply: "You are not set up for Athena yet."
- Answers and alerts use Adaptive Cards. Shadow alerts in Teams (later) have "Correct" and "Wrong" buttons that write `review_marks`.
- SharePoint search: Microsoft Graph `/search/query`, restricted to the allowlisted site paths. **Permission trimming per user needs delegated auth (Teams SSO + on-behalf-of).** App-only auth does not trim results by user. Build the delegated path; record the decision; see G4.
- Database: SQLite locally, Azure Database for PostgreSQL in production (Alembic migrations from M5).
- Deploy: the user runs it. Write the steps in `docs/RUNBOOK.md`.

## 15. Pilot rules

| ID | Name | Trigger | Action | Delivery | Receiver |
|---|---|---|---|---|---|
| R1 | Ask Anka | Any question | answer | — | The person who asks |
| R2 | Late-task alert | Every 15 minutes | notify | now | DM/AM, then hub leader |
| R3 | Daily exception digest | Each work day before the shift | notify | digest | Hub leader |
| R4 | Pre-call client brief | "Brief me on <client>" | answer | — | The CSM or DM/AM who asks |
| R5 | Weekly client report draft | Weekly | draft | now | BA |

Rule details:
- R2 values come from the hub leader (G8). Keep them in the rule file.
- R3 with no items sends one line: "No exceptions today."
- If data is stale, R3 says "Data is not current" and never "All on target".
- R5 numbers are computed in code. Each number has a query ID in the slide notes. The model writes only the comments, from the computed numbers. The BA reviews and sends. Athena never sends it to the client.
=== END FILE ===

=== FILE: docs/BUILD_PLAN.md ===
# Athena — build plan

Do the milestones in order. Inside a milestone, do the tasks in order. A task with a gate: build and test its fixture part now. Leave the live part for when the gate opens.

## Release 1 — Search and answer

### M1 Foundation (no gate)
- **M1.1** `pyproject.toml` with the package `athena` and the `athena` CLI entry point. Dependencies: pydantic>=2, pyyaml, sqlalchemy>=2, httpx, typer, croniter, tzdata, openai, msal, python-pptx. Dev: pytest, ruff. Done when `athena --help` works.
- **M1.2** Config models and loader for rules, personas, owner map, allowlist, metrics, models, smartsheet map. `athena rules validate`. Tests: the seed files load; a broken file fails with the file name, field and reason.
- **M1.3** Database layer and all tables in SPEC section 9. `DATABASE_URL` from the environment; default `sqlite:///athena.db`.
- **M1.4** Kill switches and `athena kill --global|--rule R2|--user <email> [--off]`.
- **M1.5** PHI module: `scrub()` and `lint()` with table-driven tests on synthetic strings.
- **M1.6** Gateway with all checks in SPEC section 6, in order, and receipts. One test for each check (pass and fail).
- **M1.7** `athena whoami --as <email>`: name, persona, clients in scope. This is the first acceptance test.

### M2 Connectors (fixture part: no gate; live parts: G1–G4)
- **M2.1** `connectors/http.py`: read-only HTTP client (GET; POST only to token endpoints and Graph `/search/query`), timeouts, 3 retries with backoff, no logging of bodies. Tests.
- **M2.2** `fixtures/make_fixtures.py`: deterministic synthetic data (fixed seed) for 3 clients: Smartsheet tasks (some late, some at risk, some done), Supaboard metrics with targets for 60 days, CS Hub tickets and health, SharePoint snippets, Entra users, and `fixtures/history/` with 60 days of task changes and some labelled "wrong" alerts for backtests. Commit the output.
- **M2.3** `connectors/base.py`: fixture/live switch by `ATHENA_MODE`, `ALLOWED_FIELDS`, `scrub()` on free text, `as_of` on each record.
- **M2.4** Smartsheet connector. Fixture: done and tested. Live: written against the Smartsheet API 2.0 (sheets, rows, columns, `modifiedAt`) using `context/smartsheet_map.yaml`. Live test waits for G1.
- **M2.5** Supaboard connector. Fixture: done and tested. Live: define the interface; implement after G2 gives the API.
- **M2.6** CS Hub connector. Fixture: done and tested. Live: define the interface; implement after G3.
- **M2.7** SharePoint search connector. Fixture: done and tested. Live: Graph `/search/query` restricted to allowlisted paths, delegated auth. Live test waits for G4.
- **M2.8** Entra connector. Fixture: done. Live: Graph users and managers. Live test waits for G4.
- **M2.9** `athena connectors check [--live]`: for each source, print count, field names and newest as_of only. No record content.

### M3 Tools and ask loop (no gate)
- **M3.1** The six tools, the registry and JSON schemas. Scope enforced through the gateway.
- **M3.2** Model layer: `StubModel` and `OpenAICompatModel`, token and cost accounting.
- **M3.3** Ask loop (R1): system prompt, 8-call limit, code-made Sources footer, "I do not know" and "Data is not current" behaviour, question log, last 6 turns.
- **M3.4** R4 brief template.
- **M3.5** Golden set: at least 20 synthetic questions across the four personas, including out-of-scope, "I do not know" and stale-data cases. `athena eval golden --model stub` passes all.
- **M3.6** `athena ask "<question>" --as <email>`.

### M4 Model bake-off (gate G5 for real endpoints)
- **M4.1** `athena eval golden --model <name>` for any model in `context/models.yaml`. Report in `reports/`. Add a summary table that compares models. Real runs wait for G5. The user runs them.

### M5 Teams and Azure (gates G4, G6, GD)
- **M5.1** Check the current Microsoft 365 Agents SDK for Python (packages, sample, local test tool). Record the choice and versions in DECISIONS.
- **M5.2** `function_app.py`: HTTP `/api/messages` → bot → ask loop; timer → `scheduler.tick()` (no live rules yet).
- **M5.3** Teams user → owner map by email. Unknown user → "You are not set up for Athena yet."
- **M5.4** Adaptive Cards for answers with sources.
- **M5.5** Postgres support and Alembic migrations.
- **M5.6** `docs/RUNBOOK.md`: local test steps, Azure resources, app settings, deploy commands, rollback, kill switch. The user deploys.

**STOP at the end of release 1.** Report to the user.

## Release 2 — Alerts, digests and drafts

### M6 Rule loop and R2 (fixture: no gate; live: G1, G8)
- **M6.1** Check types `threshold` and `absence` with all ops in SPEC section 4. Table-driven tests.
- **M6.2** Scheduler `tick()`: due rules by cron and time zone; freshness; check; open, update and close alerts. `athena tick`.
- **M6.3** Ladder: steps, reminder, escalation, message limit of 2. Tests with a fake clock.
- **M6.4** Message templates. The model writes from the structured payload only. Plain template if the model fails.
- **M6.5** Shadow mode and `athena review`.
- **M6.6** `athena backtest R2 --days 30` on fixture history.
- **M6.7** Automatic phase demotion from `max_wrong_rate`.

### M7 Digest and R3 (no gate)
- **M7.1** `digest.py`: collect digest items for each user and send one message at their digest time. "No exceptions today." when empty. "Data is not current" when stale.
- **M7.2** R3 rule live in fixture mode. Delivery routing: `now` versus `digest`.

### M8 Report builder and R5 (gate G7 for the real template)
- **M8.1** `reports/wbr.py`: compute the numbers in code, each with a query ID; fill a PPTX template with python-pptx (make a plain default template in `context/templates/` until G7); the model writes the comments from the numbers only; save to `drafts/`; notify the BA.
- **M8.2** `athena stats`: the measurements in SPEC section 12.

### M9 Platform test (no gate)
- **M9.1** Use the `/new-rule` procedure to add: "Alert the CSM when a CS Hub ticket has no reply for 24 hours. Escalate to the CS lead after 8 hours more." Write only YAML. If code must change, record the gap in DECISIONS, fix the platform in a general way (not for this rule only), then add the rule again with YAML only.

**STOP at the end of release 2.** Report to the user. Later releases need management decisions. Do not start them.
=== END FILE ===

=== FILE: docs/PROGRESS.md ===
# Athena — progress

Tick each task when it meets the definition of done in CLAUDE.md. Add a one-line note.

## Release 1
- [x] M0 Scaffold from ATHENA_BOOTSTRAP.md
- [ ] M1.1 Package, pyproject, CLI entry point
- [ ] M1.2 Config models, loader, `athena rules validate`
- [ ] M1.3 Database layer and tables
- [ ] M1.4 Kill switches
- [ ] M1.5 PHI scrub and lint
- [ ] M1.6 Gateway and receipts
- [ ] M1.7 `athena whoami`
- [ ] M2.1 Read-only HTTP client
- [ ] M2.2 Synthetic fixture generator
- [ ] M2.3 Connector base
- [ ] M2.4 Smartsheet connector (fixture) — live: G1
- [ ] M2.5 Supaboard connector (fixture) — live: G2
- [ ] M2.6 CS Hub connector (fixture) — live: G3
- [ ] M2.7 SharePoint search connector (fixture) — live: G4
- [ ] M2.8 Entra connector (fixture) — live: G4
- [ ] M2.9 `athena connectors check`
- [ ] M3.1 Six tools and registry
- [ ] M3.2 Model layer (stub, OpenAI-compatible)
- [ ] M3.3 Ask loop (R1)
- [ ] M3.4 Brief template (R4)
- [ ] M3.5 Golden set and `athena eval golden`
- [ ] M3.6 `athena ask`
- [ ] M4.1 Model bake-off harness — real runs: G5
- [ ] M5.1 Agents SDK check and decision
- [ ] M5.2 Azure Functions entry point — G6, GD
- [ ] M5.3 Teams user mapping
- [ ] M5.4 Adaptive Cards
- [ ] M5.5 Postgres and Alembic
- [ ] M5.6 RUNBOOK

## Release 2
- [ ] M6.1 Check types
- [ ] M6.2 Scheduler tick
- [ ] M6.3 Ladder
- [ ] M6.4 Message templates
- [ ] M6.5 Shadow mode and review
- [ ] M6.6 Backtest
- [ ] M6.7 Automatic phase demotion
- [ ] M7.1 Digest
- [ ] M7.2 R3 and delivery routing
- [ ] M8.1 Report builder (R5) — real template: G7
- [ ] M8.2 `athena stats`
- [ ] M9.1 Platform test (rule file only)

## Log
- M0: scaffold written from the bootstrap.
=== END FILE ===

=== FILE: docs/BLOCKERS.md ===
# Athena — blockers

Gates that only a person can open. Claude Code updates the status and adds "stuck" items. The user marks a gate `open` when it is done, and adds non-secret details (for example sheet IDs or column names). Secrets go only in `.env`.

| Gate | Needed | From | Blocks | Status |
|---|---|---|---|---|
| G1 | Smartsheet read token (in `.env`); sheet ID for each pilot client; column names for task, owner, due, status | Ops / Smartsheet admin | M2.4 live, M6 live | closed |
| G2 | Supaboard / Intelligence API documents and read-only key | Supaboard | M2.5 live | closed |
| G3 | CS Hub API read access to tickets and health | Vishal | M2.6 live | closed |
| G4 | Entra app registration; Graph User.Read.All and Sites.Selected with grants on the allowlisted sites; admin consent; Teams SSO for delegated search; list of SharePoint sites with client context, confirmed free of PHI | IT (Shivesh) | M2.7 live, M2.8 live, M5 | closed |
| G5 | Open-weight model endpoint(s) under a contract that covers our data; PHI decision | Madhav | M4 real runs, any live answers | closed |
| G6 | Azure Bot registration; permission to install the Teams app for pilot users | IT | M5 | closed |
| G7 | Standard WBR template (.pptx) | BA team | M8 real template | closed |
| G8 | Values for "late" and "at risk"; work days; work hours and digest time of each pilot user | Hub leader, pilot users | R2 and R3 live | closed |
| G9 | 20 real questions for each pilot persona, with correct answers | Pilot users | Real eval | closed |
| G10 | Real owner list: client, hub, hub leader, DM/AM, CSM, BA | Ops | Live mode | closed |
| GD | Azure subscription and resource group; the user deploys | IT / Madhav | Production | closed |

## Stuck items
(none)
=== END FILE ===

=== FILE: docs/DECISIONS.md ===
# Athena — decisions

## Decided before the build
- Codename: Athena. It is the first build of Anka OS.
- One platform: a new job is a new rule file, not new code.
- Rules decide; the AI model only writes text and selects read-only tools.
- Open-weight model preferred. The model can be changed (one interface). A classifier such as Jev comes later, for triage.
- Read only. Four action types: answer, notify, draft, write. Write is disabled in releases 1 and 2.
- Athena is the only system that sends management alerts. CS Hub and the workflow tools give data.
- No agent framework, no memory framework, no vector database.
- Release 1 = search and answer. Release 2 = alerts, digests and report drafts.
- Athena does not read email content or Teams chat content.
- Default delivery is `digest`. `now` only for items a person must do today.
- Claude Code does not set dates, targets or pass marks. Management sets them.

## Open (need the user)
- Microsoft 365 Copilot licences: if Anka has them, test Copilot for document search before relying on our own search.
- SharePoint search auth: delegated (Teams SSO + on-behalf-of) for per-user trimming, or app-only with a strict site allowlist.
- PHI position and model hosting (G5).
- Platform owner: the person who reviews new tools and rule files.

## Made during build
(Claude Code adds entries here: date, choice, reason, how to reverse.)
=== END FILE ===

=== FILE: .claude/settings.json ===
{
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [
      "Bash(python *)",
      "Bash(python3 *)",
      "Bash(.venv/bin/python *)",
      "Bash(.venv/bin/pip *)",
      "Bash(.venv/bin/pytest *)",
      "Bash(.venv/bin/ruff *)",
      "Bash(.venv/bin/athena *)",
      "Bash(pip install *)",
      "Bash(pytest *)",
      "Bash(ruff *)",
      "Bash(athena *)",
      "Bash(git status *)",
      "Bash(git add *)",
      "Bash(git commit *)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(mkdir *)",
      "WebFetch(domain:learn.microsoft.com)",
      "WebFetch(domain:developers.smartsheet.com)",
      "WebFetch(domain:docs.python.org)"
    ],
    "ask": [
      "Bash(az *)",
      "Bash(func *)",
      "Bash(pip uninstall *)",
      "Bash(git reset *)",
      "Bash(git checkout *)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./secrets/**)",
      "Bash(git push *)",
      "Bash(rm -rf *)",
      "Bash(curl *)",
      "Bash(wget *)"
    ]
  }
}
=== END FILE ===

=== FILE: .claude/skills/next/SKILL.md ===
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
=== END FILE ===

=== FILE: .claude/skills/status/SKILL.md ===
---
name: status
description: Show the Athena build status, the open gates, and what the user must do next. Makes no changes.
---

# Athena status

Make no changes to files. Read `docs/PROGRESS.md`, `docs/BLOCKERS.md` and `docs/DECISIONS.md`. Then show:

1. Progress: tasks done / total, for release 1 and release 2.
2. The current task.
3. Closed gates that block the next tasks, with what the user must give and from whom.
4. Open decisions.
5. Stuck items, if any.
6. One command the user can run now to see Athena work (fixture mode).
=== END FILE ===

=== FILE: .claude/skills/new-rule/SKILL.md ===
---
name: new-rule
description: Turn a plain-language use case into an Athena rule file. Use when the user describes a new alert, digest item or report for Athena.
---

# Add a rule from a description

Use case: $ARGUMENTS

1. Map the use case to:
   - a source that exists in `athena/connectors/`,
   - a check type that exists (`threshold` or `absence`) with existing ops,
   - an action type: `notify` or `draft` only (never `write`, never a client recipient),
   - a delivery: `digest` unless a person must act today,
   - owners and a ladder from the owner-map roles.
2. Write `rules/<next free ID>.yaml` with `mode: shadow` and `phase: 1`.
3. Run `athena rules validate`, then `athena backtest <ID> --days 30` on fixtures. Report the alerts per person per day.
4. Do **not** write Python code in this procedure. If the rule needs a new source, field, check type or op, stop. Record a "platform gap" under "Made during build" in `docs/DECISIONS.md`, with the exact need, and tell the user.
5. Commit: `<ID>: add rule <name> (shadow)`.
=== END FILE ===

=== FILE: .env.example ===
# Copy to .env and fill in. Never commit .env. Claude Code must never read .env.
ATHENA_MODE=fixture                  # fixture | live
DATABASE_URL=sqlite:///athena.db
INTERNAL_EMAIL_DOMAINS=fixture.local # comma-separated real domains in live mode
DEFAULT_TZ=Asia/Kolkata

# G1 Smartsheet
SMARTSHEET_TOKEN=

# G2 Supaboard / Intelligence
SUPABOARD_BASE_URL=
SUPABOARD_API_KEY=

# G3 CS Hub
CSHUB_BASE_URL=
CSHUB_API_KEY=

# G4 Microsoft Graph / Entra
GRAPH_TENANT_ID=
GRAPH_CLIENT_ID=
GRAPH_CLIENT_SECRET=

# G5 Models (one block for each candidate in context/models.yaml)
MODEL_A_BASE_URL=
MODEL_A_API_KEY=

# G6 Teams bot
BOT_APP_ID=
BOT_APP_PASSWORD=
=== END FILE ===

=== FILE: .gitignore ===
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
*.db
reports/
drafts/
secrets/
.python_packages/
local.settings.json
=== END FILE ===

=== FILE: rules/R1.yaml ===
id: R1
name: Ask Anka
trigger: {question: any}
action: answer
tools: [get_tasks, get_metrics, get_tickets, search_documents, get_owner, get_client_profile]
max_tool_calls: 8
data_max_age: 24h
template: ask_default
phase: 1
mode: live
=== END FILE ===

=== FILE: rules/R2.yaml ===
id: R2
name: Late-task alert
trigger: {cron: "*/15 * * * *", tz: Asia/Kolkata}
source: smartsheet.tasks
check:
  type: threshold
  key: task_id
  severities:            # checked in this order; first match wins. Values from the hub leader (G8).
    late:
      - {field: due, op: before, value: now}
      - {field: status, op: ne, value: Complete}
    at_risk:
      - {field: due, op: within, value: 4h}
      - {field: last_update, op: older_than, value: 2h}
      - {field: status, op: ne, value: Complete}
data_max_age: 30m
owner: owner_map.client.dm_am
ladder:
  - {after: 0h, to: dm_am}
  - {after: 4h, to: hub_leader}
renudge_after: 2h
close_when: {cleared: true}
message: {writer: model, template: late_task_alert}
action: notify
delivery: now
phase: 1
mode: shadow
max_wrong_rate: 0.2     # placeholder for demotion logic; management sets the real value
=== END FILE ===

=== FILE: rules/R3.yaml ===
id: R3
name: Daily exception digest
trigger: {cron: "30 8 * * 1-5", tz: Asia/Kolkata}   # confirm work days and time (G8)
source: supaboard.metrics
check:
  type: threshold
  key: client_metric
  severities:
    below_target:
      - {field: actual, op: lt_field, value: target}
include_open_alerts: [R2]
data_max_age: 24h
owner: owner_map.client.hub_leader
ladder:
  - {after: 0h, to: hub_leader}
message: {writer: model, template: exception_digest}
empty_message: "No exceptions today."
action: notify
delivery: digest
phase: 1
mode: shadow
max_wrong_rate: 0.2
=== END FILE ===

=== FILE: rules/R4.yaml ===
id: R4
name: Pre-call client brief
trigger: {question: brief}        # questions that start with "brief" or "brief me"
action: answer
tools: [get_tickets, get_metrics, get_tasks, search_documents, get_client_profile, get_owner]
max_tool_calls: 8
data_max_age: 24h
template: client_brief
sections: [health, open_tickets, metrics, open_tasks, recent_documents]
phase: 1
mode: live
=== END FILE ===

=== FILE: rules/R5.yaml ===
id: R5
name: Weekly client report draft
trigger: {cron: "0 8 * * 1", tz: Asia/Kolkata}
source: supaboard.metrics
clients: [northwind_ortho, bluefield_imaging]
builder:
  type: wbr
  template: context/templates/wbr.pptx     # real template from the BA team (G7)
  period: last_week
data_max_age: 24h
notify: owner_map.client.ba
action: draft
delivery: now
phase: 1
mode: live
=== END FILE ===

=== FILE: personas/hub_leader.yaml ===
persona: hub_leader
scope: clients where hub_leader = me
rules: [R1, R2, R3]
sources: [smartsheet, supaboard, cs_hub, sharepoint]
sharepoint_sites: client_context
work_hours: "10:00-19:00"      # confirm (G8)
digest_time: "09:00"           # confirm (G8)
tz: Asia/Kolkata
must_not: [client_send, data_change]
=== END FILE ===

=== FILE: personas/dm_am.yaml ===
persona: dm_am
scope: clients where dm_am = me
rules: [R1, R2, R4]
sources: [smartsheet, supaboard, cs_hub, sharepoint]
sharepoint_sites: client_context
work_hours: "10:00-19:00"      # confirm (G8)
digest_time: "09:00"
tz: Asia/Kolkata
must_not: [client_send, data_change]
=== END FILE ===

=== FILE: personas/csm.yaml ===
persona: csm
scope: clients where csm = me
rules: [R1, R4]
sources: [smartsheet, supaboard, cs_hub, sharepoint]
sharepoint_sites: client_context
work_hours: "17:00-02:00"      # US-facing hours; confirm (G8)
digest_time: "17:00"
tz: Asia/Kolkata
must_not: [client_send, data_change]
=== END FILE ===

=== FILE: personas/ba.yaml ===
persona: ba
scope: clients where ba = me
rules: [R1, R5]
sources: [supaboard, sharepoint]
sharepoint_sites: client_context
work_hours: "10:00-19:00"      # confirm (G8)
digest_time: "09:00"
tz: Asia/Kolkata
must_not: [client_send, data_change]
=== END FILE ===

=== FILE: context/owner_map.yaml ===
# SYNTHETIC fixture owner map. The real map (G10) replaces it in live mode only, from a file
# outside Git or a private branch decided by the user. Never commit real names here.
people:
  hl.key@fixture.local:   {name: Hub Leader Key,   persona: hub_leader}
  hl.small@fixture.local: {name: Hub Leader Small, persona: hub_leader}
  dm.one@fixture.local:   {name: DM One,  persona: dm_am}
  dm.two@fixture.local:   {name: DM Two,  persona: dm_am}
  csm.one@fixture.local:  {name: CSM One, persona: csm}
  csm.two@fixture.local:  {name: CSM Two, persona: csm}
  ba.one@fixture.local:   {name: BA One,  persona: ba}
clients:
  northwind_ortho:
    name: Northwind Orthopedics
    hub: key_clients
    hub_leader: hl.key@fixture.local
    dm_am: dm.one@fixture.local
    csm: csm.one@fixture.local
    ba: ba.one@fixture.local
  bluefield_imaging:
    name: Bluefield Imaging
    hub: key_clients
    hub_leader: hl.key@fixture.local
    dm_am: dm.two@fixture.local
    csm: csm.one@fixture.local
    ba: ba.one@fixture.local
  cedar_family_clinic:
    name: Cedar Family Clinic
    hub: small_clients
    hub_leader: hl.small@fixture.local
    dm_am: dm.two@fixture.local
    csm: csm.two@fixture.local
    ba: ba.one@fixture.local
=== END FILE ===

=== FILE: context/allowlist.yaml ===
sharepoint_sites:
  client_context:
    - "https://example.sharepoint.com/sites/client-context"   # real sites come from G4
internal_email_domains: [fixture.local]                       # real domains come from .env in live mode
=== END FILE ===

=== FILE: context/glossary.yaml ===
# Plain definitions of Anka terms that the model may need. Synthetic starter entries.
hub: A group of clients that one hub leader manages.
DM/AM: Delivery manager / account manager. Owns the daily delivery for a set of clients.
CSM: Client success manager. Owns the client relationship.
BA: Business analyst. Builds client reports.
WBR: Weekly business review report for a client.
=== END FILE ===

---

## Part 4 — Notes for the user (not for Phase A)

- **Why fixture first:** Claude Code can build and test almost all of release 1 and release 2 before anyone gives access. When a gate opens, it only adds the live part and the live test.
- **Where to look:** `docs/PROGRESS.md` for progress, `docs/BLOCKERS.md` for what it needs from you, `docs/DECISIONS.md` for choices it made.
- **How to stop it:** press Esc. Type `/next` to continue later. Nothing is deployed or pushed unless you do it.
- **When release 1 is done:** run `athena ask` yourself in live mode on 2 real clients. Then show it to the pilot users and collect their real questions (G9).
