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
| G7 | Standard WBR template (.pptx) | BA team | M8 real template | closed — plain default template in use |
| G8 | Values for "late" and "at risk"; work days; work hours and digest time of each pilot user | Hub leader, pilot users | R2 and R3 live | closed — provisional values in DECISIONS |
| G9 | 20 real questions for each pilot persona, with correct answers | Pilot users | Real eval | closed — 80 draft questions in tests/golden/persona_questions.yaml |
| G10 | Real owner list: client, hub, hub leader, DM/AM, CSM, BA | Ops | Live mode | closed |
| GD | Azure subscription and resource group; the user deploys | IT / Madhav | Production | closed |

## Live parts waiting
- M2.4 Smartsheet: live reader written (API 2.0, mock-tested). Needs G1: token in `.env`, real sheet IDs and column names in `context/smartsheet_map.yaml`. Then the user runs `athena connectors check --live`.
- M2.5 Supaboard: interface defined in `athena/connectors/supaboard.py`. Needs G2 API documents to implement.
- M2.6 CS Hub: interface defined in `athena/connectors/cshub.py`. Needs G3 read access to implement.
- M2.7 SharePoint: live Graph search written (delegated, on-behalf-of, allowlisted paths, mock-tested). Needs G4 app registration, consent and Teams SSO.
- M2.8 Entra: live Graph users written (app-only, mock-tested). Needs G4.

- M8.1 R5 report: builder done with a plain default template (`context/templates/wbr.pptx`). Needs G7: the BA team's standard template.
- M4.1 bake-off: harness done. Needs G5 for real model runs (the user runs them).
- M5.2 Teams/Azure: code and tests done. Needs G6 and GD to run for real.

## Stuck items
(none)
