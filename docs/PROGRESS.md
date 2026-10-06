# Athena — progress

Tick each task when it meets the definition of done in CLAUDE.md. Add a one-line note.

## Release 1
- [x] M0 Scaffold from ATHENA_BOOTSTRAP.md
- [x] M1.1 Package, pyproject, CLI entry point
- [x] M1.2 Config models, loader, `athena rules validate`
- [x] M1.3 Database layer and tables
- [x] M1.4 Kill switches
- [x] M1.5 PHI scrub and lint
- [x] M1.6 Gateway and receipts
- [x] M1.7 `athena whoami`
- [x] M2.1 Read-only HTTP client
- [x] M2.2 Synthetic fixture generator
- [x] M2.3 Connector base
- [ ] M2.4 Smartsheet connector (fixture) — live: G1 — fixture done; live waits for G1
- [ ] M2.5 Supaboard connector (fixture) — live: G2 — fixture done; live waits for G2
- [ ] M2.6 CS Hub connector (fixture) — live: G3 — fixture done; live waits for G3
- [ ] M2.7 SharePoint search connector (fixture) — live: G4 — fixture done; live waits for G4
- [ ] M2.8 Entra connector (fixture) — live: G4 — fixture done; live waits for G4
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
- M1.1: pyproject, athena package, Typer CLI; athena --help works.
- M1.2: Pydantic models for all config; errors name file, field, reason; added synthetic metrics/models/smartsheet_map seeds.
- M1.3: All SPEC 9 tables plus rule_state (phase override, staleness); DATABASE_URL, default sqlite:///athena.db.
- M1.4: Global/rule/user switches in DB; athena kill lists, sets and clears them.
- M1.5: scrub() masks SSN, DOB, IDs, phones, external emails, names after patient/pt/member; lint() returns labels; table-driven tests.
- M1.6: Nine checks in SPEC order, receipts for every outcome incl. refusals, held messages released in work hours, digest queue.
- M1.7: Shows name, persona, rules, hours and clients in scope; unknown users get the not-set-up message.
- M2.1: GET only, POST only to token endpoints and Graph /search/query; 3 retries with backoff and Retry-After; no bodies or query strings logged.
- M2.2: Seed 42, fixed anchor; tasks (late/at-risk/done + one PHI-like row), 60 days metrics, tickets, stale health for one client, docs, users, 60-day history + labels.
- M2.3: ATHENA_MODE switch, per-dataset ALLOWED fields, scrub on free text, source + as_of on every record, fixture times shifted to the clock.
- M2.4: Fixture tasks done; live API 2.0 reader tested with a mock; live test waits for G1.
- M2.5: Fixture metrics with targets and query IDs; live interface documented; waits for G2.
- M2.6: Fixture tickets and health (one client stale on purpose); live interface documented; waits for G3.
- M2.7: Fixture word search; live Graph /search/query with allowlisted paths and on-behalf-of token, mock-tested; live test waits for G4.
- M2.8: Fixture users; live Graph /users with managers and paging, mock-tested; live test waits for G4.
