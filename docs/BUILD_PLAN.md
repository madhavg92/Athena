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
