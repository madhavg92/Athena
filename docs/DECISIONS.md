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
Each item has a PROVISIONAL answer, decided in the build session at the user's request ("make decisions"). Athena is built to work with it; change it when management decides.
- Microsoft 365 Copilot licences — PROVISIONAL: assume none; Athena does its own SharePoint search. If Anka has licences, test Copilot for document search before relying on Athena's.
- SharePoint search auth — PROVISIONAL: delegated (Teams SSO + on-behalf-of), so results are trimmed to what each user may see. App-only is not used for search.
- PHI position and model hosting (G5) — PROVISIONAL: no live data goes to any model until a model host is under a contract that covers the data (`contract_covers_data: yes`). Preferred: an open-weight model hosted in Anka's own Azure tenant. Until then: the stub model and synthetic data only.
- Platform owner — PROVISIONAL: Madhav reviews new tools and rule files until someone is named.

## Provisional values (G8, G9, G10), synthetic until replaced
- G8 "late": due time has passed and status is not Complete. "At risk": due within 4 hours and no update for 2 hours. Work days Monday to Friday. Hours: hub leader, DM/AM and BA 10:00–19:00 IST; CSM and CS lead 17:00–02:00 IST. Digest: hub leader 09:00 IST. R3 runs at 08:30 IST. R2 reminder after 2h, escalation after 4h. R6: no reply for 24h, reminder after 4h, escalation to the CS lead after 8h. `max_wrong_rate` 0.2 everywhere (a placeholder; management sets it).
- G9: `tests/golden/persona_questions.yaml` — 80 draft questions (20 for each pilot persona) written from common RCM management questions on synthetic clients. Stub baseline 69/80; the misses need a real model. Replace with pilot users' real questions and answers.
- G10: the synthetic owner map stays in `context/owner_map.yaml`. The real one must live outside Git (decision for the user: a private repo or a file in Azure storage, loaded with `ATHENA_HOME`).

## Made during build
(Claude Code adds entries here: date, choice, reason, how to reverse.)
- 2026-10-06 — Ruff: E501 off (the formatter wraps code; long f-string messages stay readable); markdown excluded from `ruff format` so seed docs are never rewritten. Reverse: edit `[tool.ruff]` in pyproject.toml.
- 2026-10-06 — Seed files added with synthetic values: `context/metrics.yaml`, `context/models.yaml`, `context/smartsheet_map.yaml`. Real values replace them when G1/G5 and the hub leader's metric meanings arrive.
- 2026-10-06 — Rule files are validated strictly (unknown keys are errors) to catch typos. Rule-specific keys used by R1–R5 are declared in `Rule`. Reverse: set `extra="allow"` on `Rule`.
- 2026-10-06 — Owner-map clients accept any role key (hub_leader, dm_am, csm, ba, and others such as cs_lead) so a new ladder role needs YAML only.
- 2026-10-06 — A rule with `action: write` fails validation (write is disabled in releases 1 and 2), in addition to the gateway refusal.
- 2026-10-06 — Extra DB fields beyond SPEC 9: `receipts.item_key` (message limit), `receipts.deliver_at` (held messages), and table `rule_state` (phase override after demotion, staleness). Reverse: drop them; nothing outside the gateway/scheduler reads them.
- 2026-10-06 — Receipt status `queued` added for notify+digest items placed in the digest queue (SPEC lists shadow|sent|held|read|acted|closed|refused). Held messages are released by `Gateway.release_held()` each tick.
- 2026-10-06 — Gateway message limit counts notify receipts with status sent, held, shadow, read or acted for one item_key and one person, so shadow runs show the same volume as live.
- 2026-10-06 — PHI: regex cannot find every name (known limit). Names are only caught after patient/pt/member/subscriber/beneficiary. The real control is G5.
- 2026-10-06 — Live `as_of` = fetch time for live queries (not the sheet's `modifiedAt`), because the query returns current data; a quiet sheet is not stale. Fixture `as_of` is set per dataset (some on purpose stale).
- 2026-10-06 — Fixture times are stored against a fixed anchor (`fixtures/meta.json`) and shifted to the clock at read time, so `athena ask` works today and tests stay deterministic.
- 2026-10-06 — MSAL token calls (Entra token endpoint) and model calls (OpenAI SDK to the model endpoint) do not go through `connectors/http.py`. Both are non-connector HTTP: token endpoints are allowed by the rules; model calls send only scrubbed prompts. Reverse: wrap both SDKs with an httpx transport from http.py.
- 2026-10-06 — Tool calls are authorised by the gateway (kill switch + scope) but do not write receipts; the question log records the tools used and the answer gets one receipt.
- 2026-10-06 — A question routed to a rule that is not in the persona's `rules` falls back to R1 (e.g. a hub leader asking for a brief gets a normal answer, not a refusal). Reverse: refuse instead in `Asker.ask`.
- 2026-10-06 — Persona `sources` are enforced in the tool registry (e.g. a BA cannot read Smartsheet tasks). `get_owner` and `get_client_profile` read Git context files and are always allowed.
- 2026-10-06 — Golden eval runs on a fresh in-memory database with the fixture anchor as the clock (fixture mode), so results are repeatable and the question log is not touched.
- 2026-10-06 — M5.1 Teams SDK: Microsoft 365 Agents SDK for Python, version 1.8.0 (latest on PyPI on this date): `microsoft-agents-hosting-core`, `microsoft-agents-hosting-aiohttp`, `microsoft-agents-authentication-msal`, `microsoft-agents-activity` (all 1.8.0); `azure-functions` 2.3.0. learn.microsoft.com was blocked from the build environment, so the API was checked in the installed package source, not the docs. The user should check the current sample (github.com/microsoft/Agents, samples/python/quickstart) before deploy. Installed as the optional group `.[teams]`.
- 2026-10-06 — Hosting in Azure Functions: the SDK's ready-made host is aiohttp. Athena wraps the Functions request in the SDK's public `HttpRequestProtocol`, validates the Bot Framework JWT with the public `JwtTokenValidator`, and calls `CloudAdapter.process_request`. Reverse: host the bot as an aiohttp App Service with `start_agent_process` and keep only the timer in Functions.
- 2026-10-06 — Teams user identity: the activity gives the Entra object ID; Athena maps it to an email with the Entra connector (users now include `id`), then to the owner map. Unknown users get "You are not set up for Athena yet."
- 2026-10-06 — Local test tool: Microsoft 365 Agents Playground (to confirm against current docs; it replaces the Bot Framework Emulator). Not run in the build environment.

- 2026-10-06 — Postgres: psycopg 3 driver (`postgresql+psycopg://`; `postgres://` URLs are normalised). SQLite keeps `create_all` for local use; Postgres tables are created only by Alembic (`athena db upgrade`). Initial migration 0001 covers all tables; tested on a temporary Postgres 16. Optional deps `.[postgres]`.
- 2026-10-06 — Metric direction: `better: higher|lower` in `context/metrics.yaml`; the Supaboard connector adds `off_target` from it. R3 now checks `off_target` on the new `supaboard.latest_metrics` dataset (latest value per client + metric), because `actual < target` is wrong for backlog, AR days and denial rate.
- 2026-10-06 — A rule whose source returns no records is treated like stale data: no new alerts and no closes, so an outage never closes open alerts.
- 2026-10-06 — Scheduler: a rule that never ran fires only within 15 minutes of a scheduled time; a missed run catches up once. `athena tick --rule R3` runs a rule now.
- 2026-10-06 — The 2-message limit applies to `delivery: now` only; digest items are one line in one daily message. Digest items are queued in shadow mode too (receipt status `shadow`).
- 2026-10-06 — `.gitignore` entries `reports/` and `drafts/` anchored to the repo root (they also matched `athena/reports/`).

- 2026-10-06 — Backtest replays `fixtures/history/` (tasks and CS Hub tickets) through the real rule loop with live delivery to memory and a 15-minute clock. A source without history is refused with a clear message. Labels with `rule_id: "*"` apply to any rule on that source.
- 2026-10-06 — Logging: JSON lines to stderr from the CLI (`ATHENA_LOG_LEVEL`, default WARNING).
- 2026-10-06 — Digests: one message per person per work day (Mon-Fri, provisional G8) at the persona digest time, sent even before work hours (SPEC: "before the shift"); items from digest rules plus open alerts of `include_open_alerts` rules in the person's scope.
- 2026-10-06 — R5 report: numbers computed in code (weekly average, target, prior week, change, status by metric direction), each with a query ID and its query in the slide notes. The model writes comments only; any comment with a number not in the computed set is replaced by plain template comments. Plain default template `context/templates/wbr.pptx` until G7. The BA gets a notice; nothing goes to the client.
- 2026-10-06 — Fixture dates (not times) shift by the calendar-day difference between the clock and the anchor.
- 2026-10-06 — M9.1 platform test: R6 "Ticket without reply" added with YAML only (`rules/R6.yaml`, `personas/cs_lead.yaml`, `cs_lead` role and a synthetic CS lead in the owner map; message template `ticket_no_reply` in `context/templates/messages.yaml`). No platform gap: the source, fields, check type, ops, ladder roles and backtest history already existed. The general pieces it relies on (any owner-map role, YAML message templates, ticket history for backtests) were built in M1.2, M6.4 and M6.6 for all rules, not for R6. Backtest (30 days, fixtures): 12 alerts; at most 2 messages per person per day.
- 2026-10-06 — Push allowed (user decision in the build session): `git push` moved from deny to ask in `.claude/settings.json`; CLAUDE.md now says push only to the branch the user named. Deploy stays with the user. Reverse: move it back to deny.
- 2026-10-06 — New read-only tools approved by the platform owner (user request in the build session: "questions will be a lot more complex"): get_denials, get_ar_aging (Supaboard), get_task_history, get_team (Smartsheet row history and resource sheet), get_client_activity (CS Hub activity log; no email or chat content), get_my_alerts (Athena's own alerts in scope). Live readers for the new datasets wait for G1–G3. Synthetic fixtures tell one consistent story (Northwind: analyst on leave, Payer B prior-auth denials CO-197, recovery plan promised by 10 Oct; Cedar: AR over 90 days rising); claim denials are derived from the denial_rate metric so numbers agree.
- 2026-10-06 — Two-way alerts (user request: "interactivity back and forth on alerts"): acknowledge (pauses reminders and escalation for 2h), snooze (4h), not useful (a review mark), ask about this alert (the ask loop with the alert as context), draft a note (shown to the user only). These change Athena's own records, not any source system; writes stay disabled. Each goes through the gateway (kill switch, the person must own the client) and writes a receipt (`action_type` acknowledge / snooze). Teams alert cards carry the same buttons; `athena alert ack|snooze|wrong|ask|draft <id>`. Reassigning or closing a task in Smartsheet would be a write: a later release, with approval.
- 2026-10-06 — Demo direction chosen by the user: "Athena proposes, you approve", shown in a generic work-chat frame (no Microsoft branding). Code decides what to propose and computes every number; wording is a template. Actions are internal messages to managers (frontline analysts are not on Teams) or drafts the user copies; nothing goes to clients. In the product this needs a "proposal" step after a rule hit (rule + suggested action + approve/edit/skip), which is not built yet.
- 2026-10-06 — Hub-leader agent (user choice: money at risk, meeting prep, ask across clients; audience hub leaders). New: `athena/core/money.py` (ranks dollars at risk in 14 days: unappealed denials before the appeal deadline, over-90 AR before timely filing; expected recovery, fee at risk, hours, the biggest move and who has room), `athena/core/meetings.py` (facts and decisions per meeting), tools get_money_at_risk, get_client_economics (persona source `economics`, hub leaders only), get_meetings. Assumptions in `context/money.yaml` are PROVISIONAL for management to set. Calendar in production needs delegated Graph Calendars.Read (titles and times only) under G4. Short client names ("Northwind") now resolve when they match exactly one client.
