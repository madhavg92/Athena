"""Meeting prep. Code gathers the facts for each meeting; the model (or a template) writes the pre-read."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from athena.core import money
from athena.core.config import AthenaConfig


def upcoming(sources: Any, user: str, now: datetime, days: int = 7) -> list[dict[str, Any]]:
    rows = [
        r for r in sources.read("entra.calendar") if (r.get("owner") or "").lower() == user.lower()
    ]
    rows = [
        r for r in rows if now - timedelta(hours=1) <= r.get("start") <= now + timedelta(days=days)
    ]
    return [dict(r.data) for r in sorted(rows, key=lambda r: r.get("start"))]


def _avg(rows: list[Any]) -> float | None:
    vals = [r.get("actual") for r in rows]
    return round(sum(vals) / len(vals), 1) if vals else None


def client_facts(cfg: AthenaConfig, sources: Any, client: str, now: datetime) -> dict[str, Any]:
    today = now.date()
    last7, prev7 = (today - timedelta(days=7)).isoformat(), (today - timedelta(days=14)).isoformat()
    changes = []
    for metric, m in cfg.metrics.items():
        rows = sources.read("supaboard.metrics", client=client, metric=metric)
        now_avg = _avg([r for r in rows if r.get("date") >= last7])
        before = _avg([r for r in rows if prev7 <= r.get("date") < last7])
        target = rows[-1].get("target") if rows else None
        if now_avg is None or before is None:
            continue
        worse = (now_avg > before) if m.better == "lower" else (now_avg < before)
        changes.append(
            {
                "metric": metric.replace("_", " "),
                "last_7_days": now_avg,
                "previous_7_days": before,
                "target": target,
                "direction": "same" if now_avg == before else ("worse" if worse else "better"),
            }
        )
    tickets = [
        t for t in sources.read("cs_hub.tickets", client=client) if t.get("status") != "closed"
    ]
    unreplied = [
        t
        for t in tickets
        if not t.get("last_reply_at") or now - t.get("last_reply_at") > timedelta(days=1)
    ]
    commitments = [
        a for a in sources.read("cs_hub.activity", client=client) if a.get("type") == "commitment"
    ]
    risks = money.at_risk(cfg, sources, [client], now)
    return {
        "client": cfg.owner_map.clients[client].name,
        "changes": changes,
        "open_tickets": len(tickets),
        "tickets_waiting_on_us": [
            {"ticket_id": t.get("ticket_id"), "subject": t.get("subject")} for t in unreplied
        ],
        "commitments": [
            {"what": a.get("summary"), "when_logged": a.get("time").date().isoformat()}
            for a in commitments
        ],
        "money_at_risk_usd": sum(r.amount_usd for r in risks),
        "top_risks": [r.lever for r in risks[:2]],
    }


def brief(
    cfg: AthenaConfig, sources: Any, user: str, meeting: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Facts for one meeting, and the decisions the user needs to make (picked by code)."""
    scope = cfg.scope_of(user)
    if meeting.get("client"):
        facts = {
            "meeting": meeting.get("title"),
            "start": meeting.get("start"),
            **client_facts(cfg, sources, meeting["client"], now),
        }
        decisions = []
        if facts["commitments"]:
            decisions.append(f"Confirm the date for: {facts['commitments'][-1]['what']}")
        if facts["tickets_waiting_on_us"]:
            decisions.append(
                f"Who replies to {', '.join(t['ticket_id'] for t in facts['tickets_waiting_on_us'][:3])} before the call"
            )
        if facts["top_risks"]:
            decisions.append(f"Whether to raise: {facts['top_risks'][0]}")
        return {**facts, "decisions": decisions[:3]}
    clients = [client_facts(cfg, sources, c, now) for c in scope]
    risks = money.at_risk(cfg, sources, scope, now)
    move = money.biggest_move(cfg, sources, risks, scope)
    team = sources.read("smartsheet.team")
    gaps = [
        f"{m.get('member')} on leave until {m.get('leave_until')} ({cfg.owner_map.clients[m.get('client')].name})"
        for m in team
        if m.get("client") in scope and m.get("on_leave_today")
    ]
    decisions = ([move.text] if move else []) + [f"Cover for {g}" for g in gaps]
    decisions += [
        f"Owner and date for: {c['commitments'][-1]['what']}" for c in clients if c["commitments"]
    ]
    return {
        "meeting": meeting.get("title"),
        "start": meeting.get("start"),
        "clients": clients,
        "money_at_risk_usd": sum(r.amount_usd for r in risks),
        "staffing_gaps": gaps,
        "decisions": decisions[:3],
    }
