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
