"""The hub leader's standing list: the things that are always open (people, blocked work, volume,
quality, clients), counted by code. Each item says whether it needs the hub leader today, using the
thresholds in context/standing.yaml. The model only writes words around these numbers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import yaml
from pydantic import BaseModel

from athena.core.config import AthenaConfig

WORK_HOURS_PER_DAY = 9


class Gap(BaseModel):
    client: str
    client_name: str
    work_type: str
    inflow_today: int
    backlog: int
    oldest_days: int
    tat_days: int
    per_fte_day: int
    need_fte: float
    present_fte: float
    gap_fte: float  # positive = short, negative = room
    over_tat: bool
    absent: list[str]
    covers: list[str]  # "Analyst B1 (leaves Eligibility 0.7 FTE short)"


class Item(BaseModel):
    key: str
    area: str
    label: str
    count: int
    detail: str
    needs_you: bool
    new_24h: int = 0
    refs: list[str] = []
    source: str


def thresholds(cfg: AthenaConfig) -> dict[str, Any]:
    return yaml.safe_load((cfg.root / "context" / "standing.yaml").read_text())


def _day(v: Any) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _today(rows: list[Any], now: datetime) -> list[Any]:
    day = now.date().isoformat()
    return [r for r in rows if str(r.get("date"))[:10] == day]


def capacity(cfg: AthenaConfig, sources: Any, clients: list[str], now: datetime) -> list[Gap]:
    """People present today against today's work, by client and work type."""
    team = [m for m in sources.read("smartsheet.team") if m.get("client") in clients]
    roster = {
        (a.get("client"), a.get("member")): a.get("status")
        for a in _today(sources.read("smartsheet.attendance"), now)
    }
    work = [
        w for w in _today(sources.read("supaboard.workload"), now) if w.get("client") in clients
    ]

    def present(m: Any) -> bool:
        return roster.get((m.get("client"), m.get("member")), "present") == "present"

    base: dict[tuple[str, str], dict[str, Any]] = {}
    for w in work:
        key = (w.get("client"), w.get("work_type"))
        own = [m for m in team if m.get("client") == key[0] and m.get("role") == key[1]]
        need = round(w.get("inflow") / w.get("per_fte_day"), 2)
        have = sum(m.get("fte") for m in own if present(m))
        base[key] = {
            "w": w,
            "need": need,
            "have": have,
            "absent": [
                f"{m.get('member')} ({roster.get((m.get('client'), m.get('member')))})"
                for m in own
                if not present(m)
            ],
        }
    out = []
    for (client, work_type), b in base.items():
        w, gap = b["w"], round(b["need"] - b["have"], 2)
        covers = []
        if gap > 0:
            for m in team:
                if (
                    m.get("client") == client
                    and present(m)
                    and work_type in (m.get("also_trained") or [])
                ):
                    own = base.get((client, m.get("role")))
                    left = round(own["need"] - own["have"] + m.get("fte"), 2) if own else None
                    covers.append(
                        f"{m.get('member')} (leaves {m.get('role')} {left:g} FTE short)"
                        if left and left > 0
                        else f"{m.get('member')} (has room)"
                    )
        out.append(
            Gap(
                client=client,
                client_name=cfg.owner_map.clients[client].name,
                work_type=work_type,
                inflow_today=w.get("inflow"),
                backlog=w.get("backlog"),
                oldest_days=w.get("oldest_days"),
                tat_days=w.get("tat_days"),
                per_fte_day=w.get("per_fte_day"),
                need_fte=b["need"],
                present_fte=b["have"],
                gap_fte=gap,
                over_tat=w.get("oldest_days") > w.get("tat_days"),
                absent=b["absent"],
                covers=covers,
            )
        )
    out.sort(key=lambda g: -g.gap_fte)
    return out


def blocked(cfg: AthenaConfig, sources: Any, clients: list[str], now: datetime) -> list[dict]:
    """Open blocked work with its age, hours lost so far and time to expiry."""
    out = []
    for b in sources.read("smartsheet.blockers"):
        if b.get("client") not in clients or b.get("status") != "open":
            continue
        opened, expires = b.get("opened_at"), b.get("expires_at")
        hours_open = max(0.0, (now - opened).total_seconds() / 3600) if opened else 0.0
        out.append(
            {
                "blocker_id": b.get("blocker_id"),
                "client": cfg.owner_map.clients[b.get("client")].name,
                "kind": b.get("kind"),
                "summary": b.get("summary"),
                "waiting_on": b.get("waiting_on"),
                "people_blocked": b.get("people_blocked") or 0,
                "hours_lost": round(
                    (b.get("people_blocked") or 0) * min(hours_open, WORK_HOURS_PER_DAY), 1
                ),
                "items_held": b.get("items_held") or 0,
                "amount_usd": b.get("amount_usd") or 0,
                "age_days": round(hours_open / 24, 1),
                "expires_in_hours": round((expires - now).total_seconds() / 3600, 1)
                if expires
                else None,
                "due": b.get("due"),
                "owner": cfg.owner_map.people[b.get("owner")].name
                if b.get("owner") in cfg.owner_map.people
                else b.get("owner"),
            }
        )
    out.sort(key=lambda r: (-r["people_blocked"], -r["amount_usd"]))
    return out


def findings(cfg: AthenaConfig, sources: Any, clients: list[str], now: datetime) -> list[dict]:
    out = []
    for f in sources.read("smartsheet.quality"):
        if f.get("client") not in clients or f.get("status") != "open":
            continue
        due = f.get("due")
        out.append(
            {
                "finding_id": f.get("finding_id"),
                "client": cfg.owner_map.clients[f.get("client")].name,
                "found_by": f.get("found_by"),
                "summary": f.get("summary"),
                "severity": f.get("severity"),
                "due": due,
                "overdue": bool(due and due < now),
            }
        )
    out.sort(key=lambda r: (not r["overdue"], r["found_by"] != "client"))
    return out


def _new(rows: list[Any], field: str, now: datetime) -> int:
    return sum(1 for r in rows if r.get(field) and now - r.get(field) <= timedelta(hours=24))


def standing_list(cfg: AthenaConfig, sources: Any, email: str, now: datetime) -> list[Item]:
    from athena.core import money

    t = thresholds(cfg)
    clients = cfg.scope_of(email)
    gaps = capacity(cfg, sources, clients, now)
    blocks = blocked(cfg, sources, clients, now)
    finds = findings(cfg, sources, clients, now)
    raw_blocks = [b for b in sources.read("smartsheet.blockers") if b.get("client") in clients]
    team = [m for m in sources.read("smartsheet.team") if m.get("client") in clients]
    roster = [
        a for a in _today(sources.read("smartsheet.attendance"), now) if a.get("client") in clients
    ]
    items: list[Item] = []

    away = [a for a in roster if a.get("status") != "present"]
    unplanned = [a for a in away if a.get("status") == "unplanned absence"]
    items.append(
        Item(
            key="absent",
            area="People",
            label="Not working today",
            count=len(away),
            detail=", ".join(f"{a.get('member')} ({a.get('status')})" for a in away)
            or "Everyone is in.",
            needs_you=bool(unplanned),
            refs=[a.get("member") for a in away],
            source="smartsheet.attendance",
        )
    )
    short = [g for g in gaps if g.gap_fte >= t["short_fte"]]
    items.append(
        Item(
            key="short",
            area="People",
            label="Work short-staffed today",
            count=len(short),
            detail="; ".join(
                f"{g.client_name.split()[0]} {g.work_type.lower()} {g.gap_fte:g} FTE short"
                + (f", cover: {g.covers[0]}" if g.covers else ", no trained cover")
                for g in short
            )
            or "Every work type has enough people.",
            needs_you=bool(short),
            refs=[f"{g.client}:{g.work_type}" for g in short],
            source="supaboard.workload",
        )
    )
    notice = [m for m in team if m.get("on_notice_until")]
    training = [m for m in team if m.get("signed_off") is False]
    items.append(
        Item(
            key="people_pipeline",
            area="People",
            label="On notice or not signed off",
            count=len(notice) + len(training),
            detail="; ".join(
                [f"{m.get('member')} leaves {_day(m.get('on_notice_until')):%d %b}" for m in notice]
                + [
                    f"{m.get('member')} sign-off due {_day(m.get('sign_off_due')):%d %b}"
                    for m in training
                ]
            )
            or "None.",
            needs_you=False,
            source="smartsheet.team",
        )
    )

    locked = [b for b in blocks if b["kind"] == "access" and b["people_blocked"]]
    expiring = [
        b
        for b in blocks
        if b["expires_in_hours"] is not None and b["expires_in_hours"] <= t["expiry_warning_hours"]
    ]
    pending_ids = [
        b
        for b in blocks
        if b["kind"] == "access"
        and b["due"]
        and b["due"] - now <= timedelta(days=t["access_due_days"])
    ]
    items.append(
        Item(
            key="access",
            area="Blocked work",
            label="Logins and access",
            count=len(locked) + len(expiring) + len(pending_ids),
            detail="; ".join(
                [
                    f"{b['people_blocked']} locked out at {b['client'].split()[0]} ({b['hours_lost']:g} hours lost so far)"
                    for b in locked
                ]
                + [
                    f"login expires in {b['expires_in_hours']:.0f} hours at {b['client'].split()[0]}"
                    for b in expiring
                ]
                + [
                    f"new joiner user ID not created at {b['client'].split()[0]}"
                    for b in pending_ids
                ]
            )
            or "No access problems.",
            needs_you=bool(locked or expiring),
            new_24h=_new([b for b in raw_blocks if b.get("kind") == "access"], "opened_at", now),
            refs=[b["blocker_id"] for b in locked + expiring + pending_ids],
            source="smartsheet.blockers",
        )
    )
    waiting = [b for b in blocks if b["kind"] == "waiting_on_client"]
    old = [b for b in waiting if b["age_days"] > t["waiting_on_client_days"]]
    items.append(
        Item(
            key="waiting_on_client",
            area="Blocked work",
            label="Waiting on the client",
            count=len(waiting),
            detail=(
                f"{sum(b['items_held'] for b in waiting)} items, ${sum(b['amount_usd'] for b in waiting):,} held; "
                f"{len(old)} older than {t['waiting_on_client_days']} days"
                + (f", oldest: {max(old, key=lambda b: b['age_days'])['summary']}" if old else "")
            )
            if waiting
            else "Nothing waiting on clients.",
            needs_you=bool(old),
            refs=[b["blocker_id"] for b in old],
            source="smartsheet.blockers",
        )
    )
    outside = [b for b in blocks if b["kind"] in ("clearinghouse", "payer_portal")]
    items.append(
        Item(
            key="clearinghouse",
            area="Blocked work",
            label="Clearinghouse and payer problems",
            count=len(outside),
            detail="; ".join(
                f"{b['summary']} ({b['items_held']} claims, ${b['amount_usd']:,})" for b in outside
            )
            or "None.",
            needs_you=False,
            refs=[b["blocker_id"] for b in outside],
            source="smartsheet.blockers",
        )
    )

    late = [g for g in gaps if g.over_tat]
    items.append(
        Item(
            key="over_tat",
            area="Volume",
            label="Work over turnaround",
            count=len(late),
            detail="; ".join(
                f"{g.client_name.split()[0]} {g.work_type.lower()}: {g.backlog} items, oldest {g.oldest_days} days (target {g.tat_days})"
                for g in late
            )
            or "All work within turnaround.",
            needs_you=False,
            refs=[f"{g.client}:{g.work_type}" for g in late],
            source="supaboard.workload",
        )
    )
    risks = money.at_risk(cfg, sources, clients, now)
    soon = [r for r in risks if r.days_left <= 2]
    items.append(
        Item(
            key="deadlines",
            area="Volume",
            label="Claims near a deadline",
            count=sum(r.claims for r in risks),
            detail=f"${sum(r.amount_usd for r in risks):,} in the next {money.assumptions(cfg)['horizon_days']} days; "
            f"{sum(r.claims for r in soon)} claims (${sum(r.amount_usd for r in soon):,}) within 2 days",
            needs_you=False,
            source="supaboard.denied_claims",
        )
    )

    overdue = [f for f in finds if f["overdue"]]
    client_found = [f for f in finds if f["found_by"] == "client"]
    items.append(
        Item(
            key="quality",
            area="Quality",
            label="Audit findings open",
            count=len(finds),
            detail=(
                f"{len(overdue)} overdue, {len(client_found)} found by the client"
                + (
                    f"; {overdue[0]['client'].split()[0]}: {overdue[0]['summary']}"
                    if overdue
                    else ""
                )
            )
            if finds
            else "None open.",
            needs_you=bool([f for f in overdue if f["found_by"] == "client"]),
            refs=[f["finding_id"] for f in overdue],
            source="smartsheet.quality",
        )
    )

    tickets = [
        x
        for x in sources.read("cs_hub.tickets")
        if x.get("client") in clients
        and x.get("status") != "closed"
        and x.get("priority") == "high"
    ]
    silent = [
        x
        for x in tickets
        if (x.get("last_reply_at") or x.get("opened_at"))
        < now - timedelta(hours=t["escalation_no_reply_hours"])
    ]
    items.append(
        Item(
            key="escalations",
            area="Clients",
            label="Escalations open",
            count=len(tickets),
            detail="; ".join(
                f"{x.get('ticket_id')} {cfg.owner_map.clients[x.get('client')].name.split()[0]}: {x.get('subject')}"
                + (" (no reply in 24 hours)" if x in silent else "")
                for x in tickets
            )
            or "None.",
            needs_you=bool(silent),
            new_24h=_new(tickets, "opened_at", now),
            refs=[x.get("ticket_id") for x in tickets],
            source="cs_hub.tickets",
        )
    )
    promises = [
        a
        for a in sources.read("cs_hub.activity")
        if a.get("client") in clients and a.get("type") == "commitment"
    ]
    items.append(
        Item(
            key="promises",
            area="Clients",
            label="Promises made to clients",
            count=len(promises),
            detail="; ".join(a.get("summary") for a in promises) or "None on record.",
            needs_you=False,
            source="cs_hub.activity",
        )
    )
    return items


NOT_VISIBLE = "Not visible to Athena: leave approvals, hiring, appraisals (HR system) and anything only in email or chat."


def report_text(cfg: AthenaConfig, items: list[Item], email: str, now: datetime) -> str:
    """The daily hub report, built from the standing list. A draft for the hub leader to send."""
    from zoneinfo import ZoneInfo

    local = now.astimezone(ZoneInfo(cfg.work_hours_of(email)[1]))
    lines = [f"Hub report, {local:%a %d %b} {local:%H:%M}"]
    area = None
    for i in items:
        if i.area != area:
            area = i.area
            lines.append(area)
        lines.append(f"- {i.label}: {i.count}. {i.detail}")
    lines.append(NOT_VISIBLE)
    return "\n".join(lines)
