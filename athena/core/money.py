"""Money at risk: dollars that will be lost soon unless someone acts. Code ranks and computes
every number; the model only writes the words. Assumptions live in context/money.yaml."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import yaml
from pydantic import BaseModel

from athena.core.config import AthenaConfig


class Risk(BaseModel):
    client: str
    client_name: str
    kind: str  # "appeal" (denials not yet appealed) | "timely_filing" (over-90 AR not yet worked)
    payer: str
    reason_code: str | None = None
    reason: str | None = None
    claims: int
    amount_usd: int
    earliest_deadline: date
    days_left: int
    expected_recovery_usd: int
    fee_at_risk_usd: int
    hours_to_work: float
    lever: str


class Move(BaseModel):
    risk: Risk
    who: str | None
    who_detail: str | None
    text: str


def assumptions(cfg: AthenaConfig) -> dict[str, Any]:
    return yaml.safe_load((cfg.root / "context" / "money.yaml").read_text())


def _day(v: Any) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def at_risk(cfg: AthenaConfig, sources: Any, clients: list[str], now: datetime) -> list[Risk]:
    a = assumptions(cfg)
    today = now.date()
    horizon = today + timedelta(days=a["horizon_days"])
    fee = {}
    for r in sources.read("supaboard.economics"):
        fee[r.get("client")] = r.get("fee_pct_of_collections") or 0
    groups: dict[tuple, dict[str, Any]] = defaultdict(
        lambda: {"claims": 0, "amount": 0, "deadline": None, "reason": None}
    )
    for c in sources.read("supaboard.denied_claims"):
        if c.get("client") not in clients or c.get("status") != "not worked":
            continue
        d = _day(c.get("appeal_deadline"))
        if today <= d <= horizon:
            g = groups[(c.get("client"), "appeal", c.get("payer"), c.get("reason_code"))]
            g["claims"] += 1
            g["amount"] += c.get("amount_usd") or 0
            g["reason"] = c.get("reason")
            g["deadline"] = min(d, g["deadline"] or d)
    for c in sources.read("supaboard.ar_over_90"):
        if c.get("client") not in clients:
            continue
        d = _day(c.get("timely_filing_deadline"))
        if today <= d <= horizon:
            g = groups[(c.get("client"), "timely_filing", c.get("payer"), None)]
            g["claims"] += 1
            g["amount"] += c.get("amount_usd") or 0
            g["deadline"] = min(d, g["deadline"] or d)
    out = []
    for (client, kind, payer, code), g in groups.items():
        rate = (
            a["appeal_success_pct"].get(code, 50) if kind == "appeal" else a["work_success_pct"]
        ) / 100
        minutes = a["minutes_per_appeal"] if kind == "appeal" else a["minutes_per_ar_claim"]
        expected = round(g["amount"] * rate)
        lever = (
            f"Appeal {g['claims']} {payer} denials ({code}) before {g['deadline']:%d %b}"
            if kind == "appeal"
            else f"Work {g['claims']} {payer} claims before timely filing ({g['deadline']:%d %b})"
        )
        out.append(
            Risk(
                client=client,
                client_name=cfg.owner_map.clients[client].name,
                kind=kind,
                payer=payer,
                reason_code=code,
                reason=g["reason"],
                claims=g["claims"],
                amount_usd=g["amount"],
                earliest_deadline=g["deadline"],
                days_left=(g["deadline"] - today).days,
                expected_recovery_usd=expected,
                fee_at_risk_usd=round(expected * fee.get(client, 0) / 100),
                hours_to_work=round(g["claims"] * minutes / 60, 1),
                lever=lever,
            )
        )
    out.sort(key=lambda r: -r.amount_usd)
    return out


def biggest_move(
    cfg: AthenaConfig, sources: Any, risks: list[Risk], clients: list[str]
) -> Move | None:
    """The single action that saves the most expected money, and who has room to do it."""
    if not risks:
        return None
    best = max(risks, key=lambda r: r.expected_recovery_usd)
    team = [
        m
        for m in sources.read("smartsheet.team")
        if m.get("client") in clients and not m.get("on_leave_today")
    ]
    spare = min(team, key=lambda m: m.get("utilisation_pct") or 999, default=None)
    who = spare.get("member") if spare else None
    detail = (
        f"{spare.get('role').lower()}, {cfg.owner_map.clients[spare.get('client')].name}, {spare.get('utilisation_pct')}% utilised"
        if spare
        else None
    )
    days = max(1, round(best.hours_to_work / 6))
    text = (
        f"{best.lever}: about {best.hours_to_work:g} hours of work, expected to recover ${best.expected_recovery_usd:,}."
        + (
            f" {who} ({detail}) has the most room; {days} day{'s' if days > 1 else ''} would cover it."
            if who
            else ""
        )
    )
    return Move(risk=best, who=who, who_detail=detail, text=text)


def economics(sources: Any, clients: list[str]) -> list[dict[str, Any]]:
    rows = [r for r in sources.read("supaboard.economics") if r.get("client") in clients]
    out = []
    for r in sorted(rows, key=lambda r: (r.get("client"), r.get("month"))):
        rev, cost, fte = r.get("revenue_usd"), r.get("cost_usd"), r.get("fte")
        out.append(
            {
                "client": r.get("client"),
                "month": r.get("month"),
                "revenue_usd": rev,
                "cost_usd": cost,
                "fte": fte,
                "revenue_per_fte_usd": round(rev / fte) if fte else None,
                "margin_pct": round(100 * (rev - cost) / rev, 1) if rev else None,
                "fee_pct_of_collections": r.get("fee_pct_of_collections"),
                "query_id": r.get("query_id"),
            }
        )
    return out
