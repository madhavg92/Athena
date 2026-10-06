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
