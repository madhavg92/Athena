"""Synthetic demo: one Monday at Anka, persona by persona.

Runs the real rule loop, gateway, digest, report builder and ask loop on fixture data with a
moving clock. Notify rules run in live mode inside the demo only, so people see the messages
they would get. Nothing leaves the process: messages are collected in memory.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import select

from athena.app import build
from athena.bot.cards import alert_card, answer_card
from athena.connectors.base import fixture_anchor
from athena.connectors.registry import Sources
from athena.core import scheduler
from athena.core.config import AthenaConfig
from athena.core.db import Alert, Database
from athena.core.gateway import MemoryDeliverer

TZ = ZoneInfo("Asia/Kolkata")
PERSONAS = {
    "dm_am": ("DM/AM", "dm.one@fixture.local"),
    "hub_leader": ("Hub leader", "hl.key@fixture.local"),
    "csm": ("CSM", "csm.one@fixture.local"),
    "ba": ("BA", "ba.one@fixture.local"),
}


class Event(BaseModel):
    persona: str
    person: str
    time: str  # local time, e.g. "Mon 09:00"
    kind: str  # alert | reminder | escalation | digest | draft | answer
    title: str
    text: str
    question: str | None = None
    card: dict[str, Any] | None = None
    note: str | None = None
    alert_id: int | None = None
    item_key: str | None = None
    severity: str | None = None
    payload: dict[str, Any] | None = None


class Demo(BaseModel):
    day: str
    events: list[Event] = Field(default_factory=list)


def _at(day: datetime, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0).astimezone(
        fixture_anchor().tzinfo
    )


QUESTIONS: dict[str, list[tuple[str, str, str | None]]] = {
    # persona -> [(time, question, note)]
    "dm_am": [
        ("11:40", "Which tasks are late for Northwind?", None),
        ("11:42", "What is the backlog for Northwind Orthopedics?", None),
        (
            "11:44",
            "Show late tasks for Cedar Family Clinic",
            "Out of scope: DM One does not own Cedar.",
        ),
    ],
    "hub_leader": [
        ("09:05", "What is the first pass rate for Bluefield Imaging?", None),
        ("09:07", "Who owns Bluefield Imaging?", None),
        (
            "09:09",
            "What is the backlog for Cedar Family Clinic?",
            "Out of scope: Cedar is in another hub.",
        ),
    ],
    "csm": [
        ("17:30", "Brief me on Northwind Orthopedics", "Pre-call brief (R4)."),
        ("17:35", "What does the escalation SOP say for Bluefield Imaging?", None),
        (
            "17:37",
            "What is the NPS for Northwind Orthopedics?",
            "Athena has no NPS data, so it must say so.",
        ),
    ],
    "ba": [
        ("08:10", "What was the average backlog for Northwind Orthopedics last week?", None),
        (
            "08:12",
            "Which tasks are late for Bluefield Imaging?",
            "BA persona has no Smartsheet access.",
        ),
    ],
}


def run(cfg: AthenaConfig, personas: list[str] | None = None) -> Demo:
    personas = personas or list(PERSONAS)
    rules = {
        k: (v.model_copy(update={"mode": "live"}) if v.action == "notify" else v)
        for k, v in cfg.rules.items()
    }
    demo_cfg = cfg.model_copy(update={"rules": rules})
    day = fixture_anchor().astimezone(TZ)  # Monday 05 Oct 2026, 11:30 IST
    now = {"t": _at(day, "08:00")}
    out = MemoryDeliverer()
    app = build(
        cfg=demo_cfg,
        db=Database("sqlite://"),
        clock=lambda: now["t"],
        deliverer=out,
        run_mode="fixture",
    )
    # one consistent day: the data is a snapshot at 11:30; only the clock moves
    snapshot = fixture_anchor()
    app.sources = Sources(
        demo_cfg, clock=lambda: now["t"], run_mode="fixture", data_clock=lambda: snapshot
    )
    demo = Demo(day=f"{day:%A %d %B %Y} (synthetic)")
    who = {email: key for key, (_, email) in PERSONAS.items() if key in personas}
    seen = {"n": 0}

    def collect(kind_hint: str | None = None) -> None:
        for person, text, action in out.sent[seen["n"] :]:
            key = who.get(person)
            if key is None:
                continue
            t = now["t"].astimezone(TZ).strftime("%a %H:%M")
            if action.type == "draft":
                kind, title = "draft", "Weekly report draft ready (R5)"
            elif action.item_key and action.item_key.startswith("digest:"):
                kind, title = "digest", "Daily exception digest (R3)"
            elif text.startswith("Reminder:"):
                kind, title = "reminder", f"Reminder ({action.rule_id})"
            elif kind_hint == "escalation":
                kind, title = "escalation", f"Escalated to hub leader ({action.rule_id})"
            else:
                kind, title = (
                    "alert",
                    f"Alert ({action.rule_id} {app.cfg.rules[action.rule_id].name})",
                )
            sev = (action.payload or {}).get("severity", "late")
            card = (
                alert_card(0, text, sev) if action.type == "notify" and kind != "digest" else None
            )
            alert_id = None
            if action.item_key and not action.item_key.startswith("digest:"):
                with app.db.session() as s:
                    row = s.scalars(select(Alert).where(Alert.item_key == action.item_key)).first()
                    alert_id = row.id if row else None
            demo.events.append(
                Event(
                    persona=key,
                    person=person,
                    time=t,
                    kind=kind,
                    title=title,
                    text=text,
                    card=card,
                    alert_id=alert_id,
                    item_key=action.item_key,
                    severity=(action.payload or {}).get("severity"),
                    payload={
                        k: v
                        for k, v in (action.payload or {}).items()
                        if not str(k).startswith("_")
                    },
                )
            )
        seen["n"] = len(out.sent)

    def at(hhmm: str) -> None:
        now["t"] = _at(day, hhmm)

    def tick(*rule_ids: str, hint: str | None = None) -> None:
        """Run these rules now; with none, only release held messages and send due digests."""
        scheduler.tick(app, force=list(rule_ids) or ["(none)"])
        collect(hint)

    def ask(persona: str, hhmm: str, question: str, note: str | None) -> None:
        at(hhmm)
        email = PERSONAS[persona][1]
        result = app.asker.ask(question, email, conversation_id=f"demo-{persona}")
        demo.events.append(
            Event(
                persona=persona,
                person=email,
                time=now["t"].astimezone(TZ).strftime("%a %H:%M"),
                kind="answer",
                title=f"Asked Athena ({result.rule_id})",
                text=result.text,
                question=question,
                card=answer_card(result, "Asia/Kolkata"),
                note=note,
            )
        )
        seen["n"] = len(out.sent)

    # 08:00 weekly report drafts (R5) -> BA
    at("08:00")
    tick("R5")
    for t, q, n in QUESTIONS["ba"] if "ba" in personas else []:
        ask("ba", t, q, n)
    # 08:30 daily exception check (R3) queues items; 09:00 hub leader digest
    at("08:30")
    tick("R3")
    at("09:00")
    tick()
    for t, q, n in QUESTIONS["hub_leader"] if "hub_leader" in personas else []:
        ask("hub_leader", t, q, n)
    # 11:30 late-task check (R2) -> DM/AM
    at("11:30")
    tick("R2")
    for t, q, n in QUESTIONS["dm_am"] if "dm_am" in personas else []:
        ask("dm_am", t, q, n)
    # 13:31 reminder to DM/AM; 15:31 escalation to hub leader
    at("13:31")
    tick("R2")
    at("15:31")
    tick("R2", hint="escalation")
    # 17:30 CSM shift: questions; 18:30 ticket-without-reply check (R6)
    for t, q, n in QUESTIONS["csm"] if "csm" in personas else []:
        ask("csm", t, q, n)
    at("18:30")
    tick("R6")
    demo.events.sort(key=lambda e: (list(PERSONAS).index(e.persona), e.time))
    return demo


def as_text(demo: Demo, limit_alerts: int = 3) -> str:
    lines = [f"Athena demo: {demo.day}", "All clients, people and numbers are synthetic.", ""]
    for key, (label, email) in PERSONAS.items():
        events = [e for e in demo.events if e.persona == key]
        if not events:
            continue
        lines += ["=" * 78, f"{label}  ({email})", "=" * 78]
        shown: dict[str, int] = {}
        for e in events:
            if e.kind in ("alert", "reminder", "escalation"):
                shown[e.kind] = shown.get(e.kind, 0) + 1
                if shown[e.kind] > limit_alerts:
                    continue
            lines.append(f"\n[{e.time}] {e.title}")
            if e.question:
                lines.append(f"  Q: {e.question}")
            if e.note:
                lines.append(f"  ({e.note})")
            lines += ["  " + ln for ln in e.text.splitlines()]
        hidden = {k: v - limit_alerts for k, v in shown.items() if v > limit_alerts}
        if hidden:
            lines.append("\n  ... and " + ", ".join(f"{v} more {k}s" for k, v in hidden.items()))
        lines.append("")
    return "\n".join(lines)


def save_json(demo: Demo, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(demo.model_dump_json(indent=1))
    return path


def save_html(demo: Demo, template: Path, path: Path, cfg: AthenaConfig | None = None) -> Path:
    """Fill the demo page template with this run's events and, when `cfg` is given, the data the
    page's interactive "Ask Athena" box needs (synthetic snapshot, suggestions, scripted answers)."""
    import json

    def js(value: Any) -> str:
        return json.dumps(value, default=str).replace("</", "<\\/")

    page = template.read_text().replace("/*DEMO_DATA*/null", js(demo.model_dump(mode="json")))
    if cfg is not None:
        page = page.replace("/*ASK_DATA*/null", js(interactive_data(cfg)))
        page = page.replace("/*SUGGESTIONS*/null", js(SUGGESTIONS))
        page = page.replace("/*CANNED*/null", js(canned_answers(cfg)))
        page = page.replace("/*INBOX*/null", js(inbox(demo)))
        page = page.replace("/*OPENS_AT*/null", js(OPENS_AT))
        page = page.replace("/*PROPOSALS*/null", js(proposals(cfg)))
        page = page.replace("/*HUB*/null", js(hub_view(cfg)))
        page = page.replace("/*DAY*/null", js(hub_day(cfg)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page)
    return path


# ---------------------------------------------------------------- interactive page data

SUGGESTIONS: dict[str, list[str]] = {
    "dm_am": [
        "Why is Northwind's backlog growing?",
        "What's driving Northwind's denials?",
        "What slips while Analyst N2 is out?",
    ],
    "hub_leader": [
        "Which client needs me most this week?",
        "Are any client commitments at risk?",
        "What should I raise with DM One today?",
    ],
    "csm": [
        "Brief me on Northwind Orthopedics",
        "What did we promise Northwind, and are we on track?",
        "Is Bluefield at risk at quarter end?",
    ],
    "ba": [
        "Draft the commentary for Northwind's weekly report.",
        "Which metrics moved most last week?",
        "Explain Cedar's AR over 90 days trend.",
    ],
}


def interactive_data(cfg: AthenaConfig) -> dict[str, Any]:
    """The synthetic snapshot the page's own tools read. It goes through the real connectors,
    so only allowlisted fields are included and free text is already scrubbed."""
    snapshot = fixture_anchor()
    sources = Sources(cfg, clock=lambda: snapshot, run_mode="fixture")

    def iso(v: Any) -> Any:
        return v.isoformat() if isinstance(v, datetime) else v

    def rows(source: str) -> list[dict[str, Any]]:
        return [
            {**{k: iso(v) for k, v in r.data.items()}, "_as_of": r.as_of.isoformat()}
            for r in sources.read(source)
        ]

    people = {e: {"name": p.name, "persona": p.persona} for e, p in cfg.owner_map.people.items()}
    clients = {
        k: {
            "name": c.name,
            "hub": c.hub,
            "roles": c.roles,
            "profile": (cfg.root / "context" / "clients" / f"{k}.md").read_text()
            if (cfg.root / "context" / "clients" / f"{k}.md").exists()
            else "",
        }
        for k, c in cfg.owner_map.clients.items()
    }
    personas = {
        k: {"scope_role": p.scope_role, "sources": p.sources, "rules": p.rules}
        for k, p in cfg.personas.items()
    }
    metrics = {k: {"meaning": m.meaning, "better": m.better} for k, m in cfg.metrics.items()}
    return {
        "now": snapshot.isoformat(),
        "max_age_hours": cfg.rules["R1"].data_max_age.total_seconds() / 3600,
        "people": people,
        "clients": clients,
        "personas": personas,
        "metrics": metrics,
        "tasks": rows("smartsheet.tasks"),
        "metric_rows": [
            {k: r[k] for k in ("client", "metric", "date", "actual", "target", "_as_of")}
            for r in rows("supaboard.metrics")
        ],
        "tickets": rows("cs_hub.tickets"),
        "health": rows("cs_hub.health"),
        "documents": rows("sharepoint.documents"),
        "claims": rows("supaboard.claims"),
        "denials": [
            {
                k: r[k]
                for k in ("client", "date", "payer", "reason_code", "reason", "count", "_as_of")
            }
            for r in rows("supaboard.denials")
        ],
        "ar_aging": rows("supaboard.ar_aging"),
        "task_history": rows("smartsheet.task_history"),
        "team": rows("smartsheet.team"),
        "activity": rows("cs_hub.activity"),
    }


def canned_answers(cfg: AthenaConfig) -> dict[str, list[dict[str, str]]]:
    """Scripted (stub model) answers to the suggested questions, for viewers who cannot use Claude."""
    snapshot = fixture_anchor()
    app = build(cfg=cfg, db=Database("sqlite://"), clock=lambda: snapshot, run_mode="fixture")
    out: dict[str, list[dict[str, str]]] = {}
    for key, questions in SUGGESTIONS.items():
        email = PERSONAS[key][1]
        out[key] = []
        for q in questions:
            r = app.asker.ask(q, email, conversation_id=f"canned-{key}-{q}")
            out[key].append({"q": q, "answer": r.answer, "footer": r.footer})
    return out


# When each person opens Athena in the demo (IST), and what is in their inbox at that moment.
OPENS_AT = {"dm_am": "Mon 13:35", "hub_leader": "Mon 15:35", "csm": "Mon 18:35", "ba": "Mon 08:15"}


def inbox(demo: Demo) -> dict[str, list[dict[str, Any]]]:
    """One item per alert (with its history: sent, reminder, escalated), plus digests and drafts."""
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in PERSONAS}
    by_alert: dict[tuple[str, int], dict[str, Any]] = {}
    for e in demo.events:
        if e.kind == "answer" or e.time > OPENS_AT[e.persona]:
            continue
        if e.alert_id is not None:
            key = (e.persona, e.alert_id)
            item = by_alert.get(key)
            if item is None:
                p = e.payload or {}
                item = {
                    "type": "alert",
                    "alert_id": e.alert_id,
                    "rule": (e.item_key or "R?").split(":")[0],
                    "severity": e.severity,
                    "client": p.get("client_name"),
                    "title": p.get("title") or p.get("subject") or p.get("item_key"),
                    "text": e.text.split(": ", 1)[-1]
                    if e.kind == "escalation"
                    else e.text.removeprefix("Reminder: "),
                    "facts": {
                        k: p.get(k)
                        for k in (
                            "item_key",
                            "due",
                            "status",
                            "owner",
                            "age",
                            "ticket_id",
                            "opened_at",
                            "last_reply_at",
                            "subject",
                        )
                        if p.get(k) not in (None, "")
                    },
                    "history": [],
                    "received": e.time,
                }
                by_alert[key] = item
                out[e.persona].append(item)
            item["history"].append({"time": e.time, "kind": e.kind})
            item["latest"] = e.time
        else:
            out[e.persona].append(
                {
                    "type": e.kind,
                    "title": e.title,
                    "text": e.text,
                    "received": e.time,
                    "latest": e.time,
                }
            )
    order = {"late": 0, "never_replied": 1, "no_reply": 2, "at_risk": 3}
    for items in out.values():
        items.sort(
            key=lambda i: (i["type"] != "alert", order.get(i.get("severity") or "", 9), i["latest"])
        )
    return out


# ---------------------------------------------------------------- proposals ("Athena proposes, you approve")
# Code decides what to propose and computes every number from the data. Wording is a template.
# Actions are internal messages to managers (frontline analysts are not on Teams) or drafts.


def proposals(cfg: AthenaConfig) -> dict[str, list[dict[str, Any]]]:
    snapshot = fixture_anchor()
    sources = Sources(cfg, clock=lambda: snapshot, run_mode="fixture")

    def first(name: str) -> str:
        return name  # synthetic names are role-like ("DM One"); real first names come with G10

    tasks = sources.read("smartsheet.tasks", client="northwind_ortho")
    late = [t for t in tasks if t.get("status") != "Complete" and t.get("due") < snapshot]
    risk = [
        t
        for t in tasks
        if t.get("status") != "Complete"
        and snapshot <= t.get("due") <= snapshot + timedelta(hours=4)
    ]
    team = sources.read("smartsheet.team")
    away = next(m for m in team if m.get("client") == "northwind_ortho" and m.get("on_leave_today"))
    spare = min(
        (m for m in team if m.get("client") == "bluefield_imaging"),
        key=lambda m: m.get("utilisation_pct"),
    )
    nw_util = max(m.get("utilisation_pct") for m in team if m.get("client") == "northwind_ortho")
    since14 = (snapshot - timedelta(days=14)).date().isoformat()
    den = [
        r
        for r in sources.read("supaboard.denials", client="northwind_ortho")
        if r.get("date") >= since14
    ]
    total = sum(r.get("count") for r in den)
    top = sum(
        r.get("count")
        for r in den
        if r.get("payer", "").startswith("Payer B") and r.get("reason_code") == "CO-197"
    )
    share = round(100 * top / total) if total else 0
    activity = sources.read("cs_hub.activity", client="northwind_ortho")
    plan = next(a for a in activity if a.get("type") == "commitment")
    due = plan.get("summary").split("by ")[-1].rstrip(".")
    due_label = datetime.strptime(f"{due} {snapshot.year}", "%d %b %Y").strftime("%a %d %b")
    leave_until = datetime.fromisoformat(away.get("leave_until")).strftime("%a %d %b")
    ticket = next(
        t
        for t in sources.read("cs_hub.tickets", client="northwind_ortho")
        if "denial" in t.get("subject", "").lower()
    )
    ba_rows = {
        r.get("metric"): r
        for r in sources.read("supaboard.latest_metrics", client="northwind_ortho")
    }
    week = [
        r
        for r in sources.read("supaboard.metrics", client="northwind_ortho", metric="backlog")
        if (snapshot - timedelta(days=8)).date().isoformat()
        <= r.get("date")
        <= (snapshot - timedelta(days=1)).date().isoformat()
    ]
    backlog_avg = round(sum(r.get("actual") for r in week) / len(week)) if week else None
    names = {e: p.name for e, p in cfg.owner_map.people.items()}
    dm, hl = names["dm.one@fixture.local"], names["hl.key@fixture.local"]

    cover_msg = (
        f"Hi {first(hl)}, {away.get('member')} (payment posting, Northwind) is on leave until {leave_until} and "
        f"{len(late)} Northwind tasks are now late. Can I borrow {spare.get('member')} from Bluefield "
        f"({spare.get('utilisation_pct')}% utilised) until then? Northwind's team is at {nw_util}%."
    )
    return {
        "dm_am": [
            {
                "id": "dm-cover",
                "time": "13:35",
                "tone": "late",
                "headline": f"{len(late)} Northwind tasks are late and {len(risk)} more are close.",
                "why": f"{away.get('member')} (payment posting) is on leave until {leave_until}; the rest of the team is at {nw_util}%.",
                "checked": ["Smartsheet tasks", "team sheet", "task history"],
                "offer": f"Ask {first(hl)} to lend {spare.get('member')} ({spare.get('role').lower()}, Bluefield) until {leave_until}?",
                "action": {
                    "kind": "send",
                    "to": "hub_leader",
                    "to_name": hl,
                    "label": f"Send to {first(hl)}",
                    "text": cover_msg,
                },
                "after": f"Sent to {hl}. I'll tell you when they reply.",
            },
            {
                "id": "dm-plan",
                "time": "13:36",
                "tone": "info",
                "headline": f"The recovery plan you promised Northwind is due {due_label}.",
                "why": f"I drafted it from the data: backlog averaged {backlog_avg} last week against a target of {int(ba_rows['backlog'].get('target'))}; "
                f"{share}% of denials in the last 14 days are Payer B prior-auth (CO-197).",
                "checked": ["CS Hub activity", "Supaboard", "denials"],
                "offer": "Review the draft outline?",
                "action": {
                    "kind": "draft",
                    "label": "Open draft",
                    "text": "Northwind recovery plan (draft)\n\n1. Cover payment posting while Analyst N2 is out (request sent to hub leader).\n"
                    f"2. Backlog: from an average of {backlog_avg} back to the target of {int(ba_rows['backlog'].get('target'))}. [Add the weekly steps]\n"
                    f"3. Denials: {share}% are Payer B prior-auth (CO-197) since Payer B started rejecting the old portal. [Add the fix and owner]\n"
                    "4. Weekly check-in with the client until back on target. [Confirm day]",
                },
                "after": "Draft saved for you. Nothing was sent.",
            },
        ],
        "hub_leader": [
            {
                "id": "hl-approve",
                "time": "15:35",
                "tone": "late",
                "needs": "dm-cover",
                "headline": f"{first(dm)} asks to borrow {spare.get('member')} from Bluefield until {leave_until}.",
                "why": f"Northwind's escalations today are staffing, not process: {away.get('member')} is on leave and the team is at {nw_util}%. "
                f"Bluefield's team is at {spare.get('utilisation_pct')}%.",
                "checked": ["team sheet", "Smartsheet tasks", "Supaboard"],
                "offer": "Approve and tell both DMs?",
                "action": {
                    "kind": "send",
                    "to": "dm_am",
                    "to_name": dm,
                    "label": "Approve",
                    "text": f"Approved: {spare.get('member')} covers Northwind payment posting until {leave_until}. I've told DM Two.",
                },
                "after": f"Approved. {dm} and DM Two have been told.",
            },
            {
                "id": "hl-plan",
                "time": "15:36",
                "tone": "info",
                "headline": "One client commitment is at risk: Northwind's recovery plan.",
                "why": f"Due {due_label}. {first(dm)} has a draft but the backlog is still above target.",
                "checked": ["CS Hub activity", "Supaboard"],
                "offer": f"Nudge {first(dm)} to share the plan by Thursday?",
                "action": {
                    "kind": "send",
                    "to": "dm_am",
                    "to_name": dm,
                    "label": f"Nudge {first(dm)}",
                    "text": "Can you share the Northwind recovery plan with me by Thursday? I'd like to review it before it goes to the client.",
                },
                "after": f"Sent to {dm}.",
            },
        ],
        "csm": [
            {
                "id": "csm-reply",
                "time": "18:35",
                "tone": "risk",
                "headline": f"Northwind asked about their denial trend ({ticket.get('ticket_id')}) and has had no reply since {ticket.get('last_reply_at').strftime('%a %d %b')}.",
                "why": f"I have the answer: {share}% of denials in the last 14 days are Payer B rejecting prior authorisations sent through its old portal.",
                "checked": ["CS Hub tickets", "denials", "client activity"],
                "offer": "Here's a reply you can paste into CS Hub. Athena never sends to clients.",
                "action": {
                    "kind": "draft",
                    "label": "Copy reply",
                    "text": "Hi team, thanks for your patience. Most of the recent rise in denials comes from one payer: "
                    f"about {share}% of denials in the last two weeks are prior-authorisation rejections from Payer B, "
                    "after it stopped accepting submissions through its old portal. We are addressing this and will include "
                    "it in the recovery plan we share with you by 10 Oct. [Check before sending]",
                },
                "after": "Copied. Paste it into CS Hub when you're ready.",
            },
        ],
        "ba": [
            {
                "id": "ba-wbr",
                "time": "08:15",
                "tone": "info",
                "headline": "Northwind's weekly report is drafted, with commentary.",
                "why": f"Backlog averaged {backlog_avg} against {int(ba_rows['backlog'].get('target'))}; denial rate {ba_rows['denial_rate'].get('actual')}% "
                f"against {ba_rows['denial_rate'].get('target')}%, mostly Payer B prior-auth. Every number has a query ID in the slide notes.",
                "checked": ["Supaboard", "denials"],
                "offer": "Review the commentary?",
                "action": {
                    "kind": "draft",
                    "label": "Open commentary",
                    "text": f"Backlog averaged {backlog_avg} last week against a target of {int(ba_rows['backlog'].get('target'))} and is still rising.\n"
                    f"Denial rate was {ba_rows['denial_rate'].get('actual')}% against {ba_rows['denial_rate'].get('target')}%; "
                    f"{share}% of denials in the last 14 days were Payer B prior-auth rejections (CO-197).\n"
                    f"First pass rate {ba_rows['first_pass_rate'].get('actual')}% against {ba_rows['first_pass_rate'].get('target')}%.",
                },
                "after": "Saved to the draft deck. You send it; Athena never sends to clients.",
            },
        ],
    }


# ---------------------------------------------------------------- hub leader agent (money, meetings, ask anything)

HUB_SUGGESTIONS = [
    "Where are we losing margin?",
    "Which client earns least per FTE, and why?",
    "If we fix the Payer B denials, what is it worth to us?",
]


def hub_view(cfg: AthenaConfig) -> dict[str, Any]:
    """Everything Athena shows Hub Leader Key, computed by the real engine at the snapshot time."""
    from athena.core import meetings, money

    snapshot = fixture_anchor()
    sources = Sources(cfg, clock=lambda: snapshot, run_mode="fixture")
    hl = "hl.key@fixture.local"
    scope = cfg.scope_of(hl)
    risks = money.at_risk(cfg, sources, scope, snapshot)
    move = money.biggest_move(cfg, sources, risks, scope)
    a = money.assumptions(cfg)
    total = sum(r.amount_usd for r in risks)
    expected = sum(r.expected_recovery_usd for r in risks)
    week = meetings.upcoming(sources, hl, snapshot - timedelta(hours=1))
    ops = meetings.brief(
        cfg, sources, hl, next(m for m in week if m["type"] == "internal"), snapshot
    )
    call = meetings.brief(
        cfg, sources, hl, next(m for m in week if m.get("client") == "northwind_ortho"), snapshot
    )
    econ = money.economics(sources, scope)
    latest = {r["client"]: r for r in econ if r["month"] == max(e["month"] for e in econ)}
    first = {r["client"]: r for r in econ if r["month"] == min(e["month"] for e in econ)}
    names = {k: cfg.owner_map.clients[k].name for k in scope}
    den14 = [
        c
        for c in sources.read("supaboard.denials", client="northwind_ortho")
        if c.get("date") >= (snapshot - timedelta(days=14)).date().isoformat()
    ]
    d_total = sum(c.get("count") for c in den14)
    d_b197 = sum(
        c.get("count")
        for c in den14
        if c.get("payer", "").startswith("Payer B") and c.get("reason_code") == "CO-197"
    )
    share = round(100 * d_b197 / d_total) if d_total else 0
    urgent = [r for r in risks if r.days_left <= 2]
    today = {
        "amount": sum(r.amount_usd for r in urgent),
        "claims": sum(r.claims for r in urgent),
        "hours": round(sum(r.hours_to_work for r in urgent), 1),
        "expected": sum(r.expected_recovery_usd for r in urgent),
        "clients": sorted({r.client_name.split(" ")[0] for r in urgent}),
    }
    rows = [
        {
            "amount": r.amount_usd,
            "client": r.client_name.split(" ")[0],
            "days_left": r.days_left,
            "what": (
                f"{r.claims} {r.payer.split(' (')[0]} denials not appealed ({r.reason_code})"
                if r.kind == "appeal"
                else f"{r.claims} {r.payer.split(' (')[0]} claims near timely filing"
            ),
        }
        for r in risks[:4]
    ]
    b197 = next(r for r in risks if r.reason_code == "CO-197")
    plan_msg = (
        f"From tomorrow until Thu, {move.who} moves to Northwind to appeal the {b197.claims} Payer B prior-auth denials "
        f"(CO-197, ${b197.amount_usd:,}, first deadline {b197.earliest_deadline:%a %d %b}). "
        "DM One: please brief them on the new Payer B portal. DM Two: Bluefield eligibility checks pause for 3 days."
    )
    nw = latest["northwind_ortho"]
    margin_rows = sorted(latest.values(), key=lambda r: r["revenue_per_fte_usd"])
    low = margin_rows[0]
    canned = {
        HUB_SUGGESTIONS[0]: (
            f"Northwind. Revenue fell from ${first['northwind_ortho']['revenue_usd']:,} to ${nw['revenue_usd']:,} a month since July "
            f"while the team stayed at {nw['fte']:g} FTE, so margin is down to {nw['margin_pct']}%. "
            f"The cause is collections: {share}% of its denials in the last 14 days are Payer B prior-auth rejections, and ${total:,} "
            f"is at risk across your clients in the next 14 days."
        ),
        HUB_SUGGESTIONS[1]: (
            f"{names[low['client']]} at ${low['revenue_per_fte_usd']:,} per FTE a month (margin {low['margin_pct']}%), against "
            + ", ".join(
                f"{names[r['client']]} at ${r['revenue_per_fte_usd']:,}" for r in margin_rows[1:]
            )
            + ". Its fee is a share of collections, and collections are down because of the Payer B denials and the posting backlog while Analyst N2 is out."
        ),
        HUB_SUGGESTIONS[2]: (
            f"About ${b197.expected_recovery_usd:,} in collections in the next two weeks if the {b197.claims} open appeals go in "
            f"(assuming {a['appeal_success_pct']['CO-197']}% are paid), which is ${b197.fee_at_risk_usd:,} of Anka's fee. "
            f"It takes about {b197.hours_to_work:g} hours of work. Fixing the portal also stops new denials: these were {share}% of Northwind's denials."
        ),
    }
    return {
        "person": {"name": cfg.owner_map.people[hl].name, "email": hl, "now": "Mon 14:40"},
        "money": {
            "time": "09:00",
            "today": today,
            "total": total,
            "expected": expected,
            "horizon": a["horizon_days"],
            "rows": rows,
            "move": move.text,
            "move_short": f"Appeal the {b197.claims} Payer B prior-auth denials at Northwind before {b197.earliest_deadline:%d %b}",
            "move_value": b197.expected_recovery_usd,
            "move_hours": b197.hours_to_work,
            "who": move.who,
            "who_detail": move.who_detail,
            "how": [
                f"Denials not yet appealed whose appeal deadline is in the next {a['horizon_days']} days, plus claims over 90 days old whose timely-filing deadline is in that window.",
                f"Expected recovery assumes {a['appeal_success_pct']['CO-197']}% of prior-auth appeals and {a['work_success_pct']}% of worked AR get paid (provisional; management sets these).",
                f"Hours assume {a['minutes_per_appeal']} minutes an appeal and {a['minutes_per_ar_claim']} minutes an AR claim.",
                "Sources: Supaboard claims and denials, the team sheet. Every number has a query ID.",
            ],
            "plan": {"to": "DM One and DM Two", "text": plan_msg},
        },
        "ops": {
            "time": "14:30",
            "title": ops["meeting"],
            "at": "15:00",
            "decisions": [
                {
                    "text": f"Move {move.who} to the Northwind Payer B appeals until Thu",
                    "why": f"${b197.expected_recovery_usd:,} expected back; Bluefield has the most room ({move.who_detail.split(', ')[-1]})",
                    "button": "Approve",
                    "done": "Approved. I've told DM One and DM Two.",
                },
                {
                    "text": "Cover posting while Analyst N2 is out until Fri",
                    "why": f"Northwind's team is at {max(m.get('utilisation_pct') for m in sources.read('smartsheet.team', client='northwind_ortho'))}%; posting backlog is growing",
                    "button": "Ask DM One for a plan",
                    "done": "Sent to DM One.",
                },
                {
                    "text": "Recovery plan for Northwind, promised for Sat 10 Oct",
                    "why": "DM One has a draft outline; it needs an owner and a review slot",
                    "button": "Review Thu 17:00",
                    "done": "Added: review with DM One, Thu 17:00. I'll prepare the pre-read.",
                },
            ],
        },
        "call": {
            "time": "Tue 18:30",
            "title": call["meeting"],
            "at": "Tue 19:00",
            "ask": [f"{t['ticket_id']}: {t['subject']}" for t in call["tickets_waiting_on_us"][:3]],
            "say": [
                f"Denials: {share}% of the last 14 days are Payer B prior-auth rejections after its portal change; appeals start tomorrow.",
                f"Backlog averaged {next(c['last_7_days'] for c in call['changes'] if c['metric'] == 'backlog'):g} last week against a target of {next(c['target'] for c in call['changes'] if c['metric'] == 'backlog'):g}; cover for posting is being arranged.",
            ],
            "owe": [c["what"] for c in call["commitments"]],
        },
        "canned": canned,
        "suggestions": HUB_SUGGESTIONS,
        # records for the page's own read-only tools (the same numbers the Python tools return)
        "risks": [
            {
                **r.model_dump(mode="json", exclude={"client", "client_name"}),
                "client": r.client_name,
            }
            for r in risks
        ],
        "economics": [{**r, "client": names[r["client"]]} for r in econ],
        "meetings": [
            {"meeting": m["title"], "start": m["start"].isoformat(), "type": m["type"]}
            for m in week
        ],
        "briefs": {"ops": ops, "northwind": call},
    }


# ---------------------------------------------------------------- the hub leader's day (standing list)

DAY_SUGGESTIONS = [
    "Who can cover Northwind posting?",
    "What are we waiting on from clients?",
    "How many hours did logins cost us today?",
]


def _ist(hhmm: str) -> datetime:
    anchor = fixture_anchor().astimezone(TZ)
    h, m = (int(x) for x in hhmm.split(":"))
    return anchor.replace(hour=h, minute=m, second=0, microsecond=0).astimezone(ZoneInfo("UTC"))


def _first(name: str) -> str:
    return name.split()[0]


def hub_day(cfg: AthenaConfig) -> dict[str, Any]:
    """Hub Leader Key's Monday, message by message. Every number comes from core/standing.py on
    the synthetic fixtures; the words are templates. Decisions only message Anka managers or make
    drafts; nothing goes to clients."""
    from athena.core import standing

    snapshot = fixture_anchor()
    sources = Sources(cfg, clock=lambda: snapshot, run_mode="fixture")
    hl = "hl.key@fixture.local"
    scope = cfg.scope_of(hl)
    people = cfg.owner_map.people
    dm = {k: people[cfg.owner_map.clients[k].dm_am].name for k in scope}
    csm = {k: people[cfg.owner_map.clients[k].csm].name for k in scope}

    # 09:00 -- the morning message: what on the standing list needs the hub leader today
    morning = _ist("09:00")
    gaps = {(g.client, g.work_type): g for g in standing.capacity(cfg, sources, scope, morning)}
    post = gaps[("northwind_ortho", "Payment posting")]
    denials = gaps[("northwind_ortho", "Denials")]
    team = [m for m in sources.read("smartsheet.team") if m.get("client") in scope]
    trained = [
        m.get("member")
        for m in team
        if "Payment posting" in (m.get("also_trained") or []) and m.get("client") == post.client
    ]
    back = standing._day(
        next(m.get("leave_until") for m in team if m.get("member") == post.absent[0].split(" (")[0])
    )
    days_out = sum(
        1
        for d in range(1, 7)
        if (morning + timedelta(days=d)).date() < back
        and (morning + timedelta(days=d)).weekday() < 5
    )
    by_return = post.backlog + post.inflow_today * (days_out + 1)
    left = round(denials.need_fte, 2)
    blocks = standing.blocked(cfg, sources, scope, morning)
    old = [
        b
        for b in blocks
        if b["kind"] == "waiting_on_client"
        and b["age_days"] > standing.thresholds(cfg)["waiting_on_client_days"]
    ]
    oldest = max(old, key=lambda b: b["age_days"])
    finding = next(f for f in standing.findings(cfg, sources, scope, morning) if f["overdue"])
    tickets = [
        t
        for t in sources.read("cs_hub.tickets")
        if t.get("client") in scope
        and t.get("status") != "closed"
        and t.get("priority") == "high"
        and not t.get("last_reply_at")
    ]
    same = len({t.get("subject") for t in tickets}) == 1 and len(tickets) > 1
    items = standing.standing_list(cfg, sources, hl, morning)
    chase = "\n".join(
        [f"{dm['northwind_ortho']}, these have waited on the client for more than 5 days:"]
        + [
            f"- {b['client']}: {b['summary']} ({b['age_days']:.0f} days, {b['items_held']} items, ${b['amount_usd']:,})"
            for b in sorted(old, key=lambda b: -b["age_days"])
        ]
        + ["Can you chase them on today's client calls and give me a date for each?"]
    )
    n2 = post.absent[0].split(" (")[0]
    rows = [
        {
            "id": "posting",
            "text": f"Northwind posting is falling behind while {n2} is out.",
            "detail": f"{post.backlog} items waiting, the oldest {post.oldest_days} days (target {post.tat_days}). {n2} is back {back:%a}. Only {', '.join(trained)} is trained to cover, and they are needed on denials.",
            "buttons": [
                {
                    "id": "move",
                    "label": f"Move {trained[0]} to posting",
                    "done": f"Sent to {dm['northwind_ortho']}. Denials will slip until {back:%a} (about {round(left * denials.per_fte_day)} a day).",
                },
                {
                    "id": "wait",
                    "label": f"Wait for {n2}",
                    "done": f"Noted. About {by_return} items will be waiting by {back:%a}; I'll tell you if the oldest passes 5 days.",
                },
            ],
        },
        {
            "id": "waiting",
            "text": f"{len(old)} things have been stuck with clients for over 5 days.",
            "detail": f"${sum(b['amount_usd'] for b in old):,} held. Oldest: {oldest['summary']} ({oldest['client'].split()[0]}, {oldest['age_days']:.0f} days).",
            "buttons": [
                {
                    "id": "chase",
                    "label": f"Ask {dm['northwind_ortho']} and {dm['bluefield_imaging']} to chase",
                    "done": f"Sent to {dm['northwind_ortho']} and {dm['bluefield_imaging']}.",
                    "draft": chase,
                }
            ],
        },
        {
            "id": "audit",
            "text": f"An error {finding['client'].split()[0]} found is past its fix date.",
            "detail": f"{finding['summary']}. The fix was due {finding['due'].astimezone(TZ):%a}.",
            "buttons": [
                {
                    "id": "date",
                    "label": f"Ask {dm['northwind_ortho']} for a date",
                    "done": f"Sent to {dm['northwind_ortho']}.",
                }
            ],
        },
        {
            "id": "tickets",
            "text": "Two clients have the same unanswered complaint."
            if same
            else f"{len(tickets)} urgent client tickets have no reply.",
            "detail": (f"“{tickets[0].get('subject')}”: " if same else "")
            + ", ".join(
                f"{t.get('ticket_id')} ({cfg.owner_map.clients[t.get('client')].name.split()[0]})"
                for t in tickets
            )
            + (". One fix may close both." if same else "."),
            "buttons": [
                {
                    "id": "reply",
                    "label": f"Ask {csm['northwind_ortho']} to reply today",
                    "done": f"Sent to {csm['northwind_ortho']}.",
                }
            ],
        },
    ]
    calm = [i for i in items if not i.needs_you]

    # 10:32 -- R9: an unplanned absence
    absence = _ist("10:32")
    auth = standing.capacity(cfg, sources, scope, absence)
    auth = next(g for g in auth if g.work_type == "Prior auth")
    cover = auth.covers[0].split(" (")[0]
    cover_left = auth.covers[0].split("leaves ")[1].rstrip(")")

    # 12:45 -- R7 escalated: still locked out after 2 hours
    esc = _ist("12:45")
    lock = next(
        b for b in standing.blocked(cfg, sources, scope, esc) if b["blocker_id"] == "BL-301"
    )
    tonight = round(lock["people_blocked"] * (_ist("18:30") - _ist("10:40")).total_seconds() / 3600)
    email = (
        "To: Northwind office manager\n"
        "Subject: MFA reset needed for 2 Anka users\n\n"
        f"Hello, two of our team ({', '.join(['Analyst N1', 'Analyst N3'])}) were locked out of the practice system at 10:40 IST. "
        "The reset code comes to you. Could you approve it first thing when you start? Until then they cannot work on your accounts.\n"
        f"Thank you, {csm['northwind_ortho']}"
    )

    # 18:50 -- the hub report, built from the standing list
    end = _ist("18:50")
    end_items = standing.standing_list(cfg, sources, hl, end)
    report = standing.report_text(cfg, end_items, hl, end)

    # data for the chat's tools and prepared answers (as of 18:50)
    end_blocks = standing.blocked(cfg, sources, scope, end)
    waiting = [b for b in end_blocks if b["kind"] == "waiting_on_client"]
    others = [
        m.get("member")
        for m in team
        if m.get("client") != post.client
        and (
            "Payment posting" in (m.get("also_trained") or []) or m.get("role") == "Payment posting"
        )
    ]
    others_auth = [
        m.get("member")
        for m in team
        if m.get("client") != auth.client
        and ("Prior auth" in (m.get("also_trained") or []) or m.get("role") == "Prior auth")
    ]
    still = [i for i in end_items if i.needs_you]
    canned = {
        "What is outstanding today?": "\n".join(
            [f"{len(rows)} things need you today:"]
            + [f"- {r['text']}" for r in rows]
            + [f"{len(calm)} other open items are moving without you."]
        ),
        DAY_SUGGESTIONS[0]: (
            f"Only {', '.join(trained)} is trained in posting, and they are needed on denials. "
            f"Moving them leaves denials {left:g} FTE short, about {round(left * denials.per_fte_day)} a day. "
            + (
                f"Also trained elsewhere: {', '.join(others)}."
                if others
                else "Nobody at Bluefield is trained in posting."
            )
        ),
        DAY_SUGGESTIONS[1]: "\n".join(
            [f"{len(waiting)} things, ${sum(b['amount_usd'] for b in waiting):,} held:"]
            + [
                f"- {b['client'].split()[0]}: {b['summary']} ({b['age_days']:.0f} days)"
                for b in sorted(waiting, key=lambda b: -b["age_days"])
            ]
        ),
        "Who else could cover prior auth?": (
            f"Only {cover} is trained in prior auth. "
            + (
                f"Elsewhere: {', '.join(others_auth)}."
                if others_auth
                else "Nobody at Northwind is."
            )
        ),
        "What slips if nobody does?": (
            f"{auth.inflow_today} prior auths due today wait until tomorrow. "
            f"With a {auth.tat_days}-day target, all of them will be late."
        ),
        DAY_SUGGESTIONS[2]: (
            f"About {lock['hours_lost']:g} hours so far: {lock['people_blocked']} people at Northwind locked out since 10:40. "
            + "; ".join(
                f"Next: a login at {b['client'].split()[0]} expires in {b['expires_in_hours']:.0f} hours ({b['owner']} has it)"
                for b in standing.blocked(cfg, sources, scope, esc)
                if b["expires_in_hours"] is not None
            )
            + "."
        ),
        "What is still open tonight?": f"{len(still)} items still need you: "
        + "; ".join(i.label.lower() for i in still)
        + ".",
    }
    hub = hub_view(cfg)
    return {
        "person": {"name": people[hl].name, "email": hl},
        "start": "08:55",
        "events": [
            {
                "id": "morning",
                "time": "09:00",
                "credit": "Rule R3, every work day at 09:00",
                "title": f"Good morning. {len(rows)} things need you today.",
                "rows": rows,
                "calm": len(calm),
                "standing": [
                    {
                        "label": i.label,
                        "count": i.count,
                        "needs_you": i.needs_you,
                        "detail": i.detail,
                    }
                    for i in items
                ],
                "suggest": ["What is outstanding today?", DAY_SUGGESTIONS[0], DAY_SUGGESTIONS[1]],
            },
            {
                "id": "absence",
                "time": "10:32",
                "credit": "Rule R9 Unplanned absence, checked every 15 minutes",
                "tone": "risk",
                "text": f"{auth.absent[0].split(' (')[0]} is out today, and nobody is on Bluefield prior auths.",
                "detail": f"No leave was booked. {auth.inflow_today} prior auths are due today. {cover} is trained; moving them leaves {cover_left[0].lower() + cover_left[1:]}.",
                "buttons": [
                    {
                        "id": "cover",
                        "label": f"Move {cover} to prior auth",
                        "done": f"Sent to {dm['bluefield_imaging']}. Eligibility checks will run late.",
                    },
                    {
                        "id": "ask",
                        "label": f"Let {dm['bluefield_imaging']} decide",
                        "done": f"Sent to {dm['bluefield_imaging']}.",
                    },
                ],
                "suggest": ["Who else could cover prior auth?", "What slips if nobody does?"],
            },
            {
                "id": "lockout",
                "time": "12:45",
                "credit": f"Rule R7 Locked out: to {dm['northwind_ortho']} at 10:45, to you after 2 hours",
                "tone": "late",
                "text": "Two Northwind analysts are still locked out.",
                "detail": f"Since 10:40: {lock['hours_lost']:g} hours lost so far, about {tonight} by tonight. The reset code goes to the client's office manager, who starts at 18:30 IST.",
                "buttons": [
                    {
                        "id": "email",
                        "draft": email,
                        "label": f"Draft the email for {csm['northwind_ortho']}",
                        "done": f"Draft sent to {csm['northwind_ortho']} to check and send. Athena never writes to clients.",
                    }
                ],
                "suggest": [DAY_SUGGESTIONS[2]],
            },
            {
                "id": "report",
                "time": "18:50",
                "credit": "Daily hub report, drafted at 18:50 from your standing list",
                "text": "Your hub report for today is ready to send.",
                "report": report,
                "suggest": ["What is still open tonight?"],
            },
        ],
        "tools": {
            "standing": [i.model_dump(mode="json") for i in end_items]
            + [{"key": "not_visible", "detail": standing.NOT_VISIBLE}],
            "capacity": [
                g.model_dump(mode="json") for g in standing.capacity(cfg, sources, scope, end)
            ],
            "blocked": [
                {**b, "due": b["due"].isoformat() if b["due"] else None} for b in end_blocks
            ],
            "quality": [
                {**f, "due": f["due"].isoformat() if f["due"] else None}
                for f in standing.findings(cfg, sources, scope, end)
            ],
            "risks": hub["risks"],
            "economics": hub["economics"],
            "meetings": hub["meetings"],
            "briefs": hub["briefs"],
        },
        "canned": canned,
    }
