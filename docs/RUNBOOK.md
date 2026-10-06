# Athena — runbook

The user runs everything in this file that touches Azure or live data. Claude Code does not deploy, push or run live mode.

## 1. Local test (fixture mode, no access needed)

```
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,teams,postgres]"
pytest -q && ruff check .
athena rules validate
athena connectors check
athena whoami --as dm.one@fixture.local
athena ask "Which tasks are late for Northwind?" --as dm.one@fixture.local
athena ask "Brief me on Northwind Orthopedics" --as csm.one@fixture.local
athena eval golden --model stub
```

Fixture data is synthetic (`fixtures/`). Times shift to "now" when read, so answers look current.

## 2. Local test of the Teams bot

1. Install Azure Functions Core Tools v4 and the Microsoft 365 Agents Playground (check the current Microsoft docs for the install command).
2. `cp local.settings.example.json local.settings.json` (gitignored). Leave the bot IDs empty for a local playground test only if the playground supports anonymous mode; otherwise fill them from G6.
3. `func start` — the bot listens on `http://localhost:7071/api/messages`.
4. Point the playground at that URL and send: `What is the backlog for Northwind Orthopedics?`
5. The Teams user must map to the owner map (by Entra object ID or UPN). Unknown users get "You are not set up for Athena yet."

## 3. Azure resources (GD, G4, G6)

One resource group (from IT), in the region IT chooses:

| Resource | Purpose | Notes |
|---|---|---|
| Function App (Python 3.11, Linux, Flex Consumption or Premium) | `function_app.py`: timer every 15 minutes + `/api/messages` | System-assigned managed identity on |
| Storage account | Required by Functions | |
| Azure Database for PostgreSQL – Flexible Server | Receipts, alerts, question log | Private access or firewall to the Function App only |
| Key Vault | All secrets | Function App reads secrets by Key Vault references |
| Application Insights | Logs and metrics | Logs hold IDs, counts and timings only |
| Azure Bot (single tenant) | Teams channel | Messaging endpoint `https://<app>.azurewebsites.net/api/messages` |
| Entra app registration (bot) | Bot identity (G6) | |
| Entra app registration (Graph) | Users (app-only `User.Read.All`) and delegated search (`Sites.Selected` grants on allowlisted sites; Teams SSO + on-behalf-of) (G4) | Admin consent by IT |

## 4. App settings

Set on the Function App. Secrets as Key Vault references (`@Microsoft.KeyVault(SecretUri=...)`), never as plain values and never in Git.

| Setting | Value |
|---|---|
| `ATHENA_MODE` | `fixture` first; `live` only after the gates for the live sources are open |
| `DATABASE_URL` | `postgresql://<user>:<password>@<server>.postgres.database.azure.com:5432/athena?sslmode=require` (Key Vault) |
| `INTERNAL_EMAIL_DOMAINS` | Anka's real email domains, comma-separated |
| `DEFAULT_TZ` | `Asia/Kolkata` |
| `SMARTSHEET_TOKEN` | G1 (Key Vault) |
| `SUPABOARD_BASE_URL`, `SUPABOARD_API_KEY` | G2 |
| `CSHUB_BASE_URL`, `CSHUB_API_KEY` | G3 |
| `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` | G4 |
| `MODEL_A_BASE_URL`, `MODEL_A_API_KEY` | G5 — only for a model with `contract_covers_data: yes` |
| `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID` / `__CLIENTSECRET` / `__TENANTID` | G6 bot app registration |

The real owner map (G10) must not be committed. Deploy it as a file outside Git (decision for the user: a private branch, or a file mounted from storage) and point Athena at a config root with `ATHENA_HOME`.

## 5. Deploy

```
az login
az account set --subscription <subscription>
# first time only: create the database tables
DATABASE_URL='<postgres url>' athena db upgrade
# deploy the code (remote build installs requirements.txt)
func azure functionapp publish <function-app-name> --python
```

Check:
1. Function App → Functions: `tick` and `messages` are listed.
2. `athena connectors check --live` from a machine with the live settings: counts, field names and times only.
3. Ask a question in Teams as a pilot user.

Rules start in `mode: shadow`. Keep notify rules in shadow for at least one week, review with `athena review`, then change `mode` to `live` in the rule file and deploy.

## 6. Rollback

- Code: redeploy the previous Git tag (`git checkout <tag> && func azure functionapp publish <app> --python`), or swap back a deployment slot if slots are used.
- Database: migrations only add tables and columns. To go back one migration: `DATABASE_URL=... alembic downgrade -1` (take a backup first; Flexible Server has point-in-time restore).
- A bad rule: set its kill switch (below), then fix the YAML and deploy.

## 7. Kill switches

Run from any machine with `DATABASE_URL` set to the production database:

```
athena kill --global              # stop everything (answers, alerts, digests, drafts)
athena kill --rule R2             # stop one rule
athena kill --user someone@anka…  # stop all actions for one person
athena kill                       # list switches that are on
athena kill --rule R2 --off       # turn a switch off again
```

Switches take effect on the next action; no deploy is needed. Every refused action writes a receipt with the reason.

## 8. Where to look

- Receipts and alerts: the Postgres tables `receipts`, `alerts`, `review_marks`.
- Measurements: `athena stats` (release 2).
- Progress and gates: `docs/PROGRESS.md`, `docs/BLOCKERS.md`, `docs/DECISIONS.md`.
