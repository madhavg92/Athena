"""Measurements from receipts and logs (SPEC 12). Records measurements only; sets no targets."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from athena.app import App
from athena.core.db import Alert, QuestionLog, Receipt, ReviewMark, as_utc


def collect(app: App, days: int = 7) -> dict[str, Any]:
    since = app.clock() - timedelta(days=days)
    with app.db.session() as s:
        receipts = [r for r in s.scalars(select(Receipt)) if as_utc(r.time) >= since]
        alerts = [a for a in s.scalars(select(Alert)) if as_utc(a.opened_at) >= since]
        marks = {
            m.alert_id: m.verdict for m in s.scalars(select(ReviewMark).order_by(ReviewMark.id))
        }
        questions = [q for q in s.scalars(select(QuestionLog)) if as_utc(q.time) >= since]

    rules: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    hours_to_close: dict[str, list[float]] = defaultdict(list)
    for a in alerts:
        r = rules[a.rule_id]
        r["alerts_opened"] += 1
        r["alerts_closed" if a.state == "closed" else "alerts_open"] += 1
        if a.id in marks:
            r[f"marked_{marks[a.id]}"] += 1
        if a.closed_at:
            hours_to_close[a.rule_id].append(
                (as_utc(a.closed_at) - as_utc(a.opened_at)).total_seconds() / 3600
            )
    for rule_id, values in hours_to_close.items():
        rules[rule_id]["median_hours_open_to_close"] = round(statistics.median(values), 1)
    cost_rule: dict[str, float] = defaultdict(float)
    cost_user: dict[str, float] = defaultdict(float)
    tokens_rule: dict[str, int] = defaultdict(int)
    for rc in receipts:
        if rc.action_type in ("notify", "draft"):
            rules[rc.rule_id or "-"][f"messages_{rc.status}"] += 1
        if rc.action_type == "draft" and rc.status != "refused":
            rules[rc.rule_id or "-"]["drafts"] += 1
        cost_rule[rc.rule_id or "-"] += rc.cost_usd or 0
        cost_user[rc.actor if rc.action_type == "answer" else (rc.recipient or "-")] += (
            rc.cost_usd or 0
        )
        tokens_rule[rc.rule_id or "-"] += (rc.tokens_in or 0) + (rc.tokens_out or 0)
    for r in rules.values():
        reviewed = r.get("marked_wrong", 0) + r.get("marked_correct", 0)
        r["wrong_rate"] = round(r.get("marked_wrong", 0) / reviewed, 3) if reviewed else None

    answered = [q for q in questions if not q.idk]
    refused_answers = sum(
        1 for rc in receipts if rc.action_type == "answer" and rc.status == "refused"
    )
    return {
        "days": days,
        "rules": {k: dict(v) for k, v in sorted(rules.items())},
        "questions": {
            "asked": len(questions),
            "answered": len(answered),
            "i_do_not_know": len(questions) - len(answered),
            "stale_answers": sum(q.stale for q in questions),
            "refused_by_gateway": refused_answers,
            "avg_latency_ms": round(sum(q.latency_ms for q in questions) / len(questions))
            if questions
            else None,
        },
        "cost_usd_by_rule": {k: round(v, 4) for k, v in sorted(cost_rule.items())},
        "tokens_by_rule": dict(sorted(tokens_rule.items())),
        "cost_usd_by_user": {k: round(v, 4) for k, v in sorted(cost_user.items()) if v},
        "not_measured": [
            "changes to drafts (needs the BA's edited version; later)",
            "alert read/acted (needs Teams card events)",
        ],
    }
