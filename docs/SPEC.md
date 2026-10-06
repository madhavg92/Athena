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
