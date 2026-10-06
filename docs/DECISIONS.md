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
