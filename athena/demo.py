"""Synthetic demo: one Monday at Anka, persona by persona.

Runs the real rule loop, gateway, digest, report builder and ask loop on fixture data with a
moving clock. Notify rules run in live mode inside the demo only, so people see the messages
they would get. Nothing leaves the process: messages are collected in memory.
"""

from __future__ import annotations

from datetime import datetime
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
