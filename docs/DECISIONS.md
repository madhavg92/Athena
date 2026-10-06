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
