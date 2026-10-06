"""Make deterministic SYNTHETIC fixture data. No real clients, people or patients.

Run: python fixtures/make_fixtures.py
All times are written relative to ANCHOR. In fixture mode the connectors shift every
time by (now - ANCHOR) so the data looks current; tests pin the clock to ANCHOR.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

ANCHOR = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)  # 11:30 Asia/Kolkata, a Monday
SEED = 42
OUT = Path(__file__).resolve().parent

CLIENTS = {
    "northwind_ortho": {"name": "Northwind Orthopedics", "dm_am": "dm.one@fixture.local"},
    "bluefield_imaging": {"name": "Bluefield Imaging", "dm_am": "dm.two@fixture.local"},
    "cedar_family_clinic": {"name": "Cedar Family Clinic", "dm_am": "dm.two@fixture.local"},
}
SHEETS = {
    "northwind_ortho": 1000000000000001,
    "bluefield_imaging": 1000000000000002,
    "cedar_family_clinic": 1000000000000003,
}
TASK_TITLES = [
    "Post payments batch",
    "Work denial queue",
    "Eligibility checks for tomorrow",
    "Prior auth follow-up",
    "Charge entry backlog",
    "AR follow-up over 90 days",
    "Credit balance review",
    "Month-end reconciliation",
    "Coding audit sample",
    "Payer portal enrolment",
]
METRICS = {
    # metric: (target, start value, daily drift, noise)
    "backlog": (300.0, 280.0, 2.5, 25.0),
    "first_pass_rate": (95.0, 95.5, -0.03, 0.8),
    "ar_days": (40.0, 38.0, 0.08, 1.5),
    "denial_rate": (8.0, 7.5, 0.02, 0.6),
}


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def write(name: str, data) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def tasks(rng: random.Random) -> list[dict]:
    rows = []
    n = 0
    for client, info in CLIENTS.items():
        for i, title in enumerate(TASK_TITLES):
            n += 1
            kind = ["late", "at_risk", "done", "ok", "ok", "late", "done", "ok", "at_risk", "ok"][i]
            if kind == "late":
                due = ANCHOR - timedelta(hours=rng.randint(2, 30))
                status, upd = "In Progress", ANCHOR - timedelta(hours=rng.randint(3, 20))
            elif kind == "at_risk":
                due = ANCHOR + timedelta(hours=rng.randint(1, 3))
                status, upd = "Not Started", ANCHOR - timedelta(hours=rng.randint(3, 8))
            elif kind == "done":
                due = ANCHOR - timedelta(hours=rng.randint(1, 20))
                status, upd = "Complete", ANCHOR - timedelta(hours=rng.randint(1, 5))
            else:
                due = ANCHOR + timedelta(hours=rng.randint(10, 72))
                status, upd = "In Progress", ANCHOR - timedelta(minutes=rng.randint(5, 50))
            rows.append(
                {
                    "task_id": f"T-{1000 + n}",
                    "client": client,
                    "title": title,
                    "owner": info["dm_am"],
                    "due": iso(due),
                    "status": status,
                    "last_update": iso(upd),
                    "sheet_id": SHEETS[client],
                    "row_id": 5000 + n,
                    "notes": "",
                }
            )
    # one row with PHI-like text to prove scrubbing (fully synthetic)
    rows[3]["title"] = "Rebill claim for patient John Doe, member ID W998877665"
    rows[3]["notes"] = "Call back on 555-010-0199"
    return rows


def metrics(rng: random.Random) -> list[dict]:
    rows = []
    for client in CLIENTS:
        for metric, (target, start, drift, noise) in METRICS.items():
            bias = {"northwind_ortho": 1.0, "bluefield_imaging": 0.6, "cedar_family_clinic": 1.3}[
                client
            ]
            for d in range(60, 0, -1):
                day = (ANCHOR - timedelta(days=d)).date()
                value = start + drift * bias * (60 - d) + rng.gauss(0, noise)
                rows.append(
                    {
                        "client": client,
                        "metric": metric,
                        "date": day.isoformat(),
                        "actual": round(value, 1),
                        "target": target,
                        "query_id": f"sb.{metric}.daily",
                        "as_of": iso(ANCHOR - timedelta(hours=3)),
                    }
                )
    return rows


def tickets(rng: random.Random) -> tuple[list[dict], list[dict]]:
    subjects = [
        "Report shows wrong payer mix",
        "Request for weekly call reschedule",
        "Question on denial trend",
        "Missing remits for last week",
        "Access to client portal",
        "Escalation: slow charge entry",
    ]
    rows, n = [], 0
    for client in CLIENTS:
        for i, subject in enumerate(subjects):
            n += 1
            opened = ANCHOR - timedelta(hours=rng.randint(4, 120))
            status = ["open", "open", "pending", "closed", "open", "closed"][i]
            last_reply = None if i == 0 else opened + timedelta(hours=rng.randint(1, 3))
            rows.append(
                {
                    "ticket_id": f"CS-{200 + n}",
                    "client": client,
                    "subject": subject,
                    "status": status,
                    "priority": ["high", "low", "medium", "low", "medium", "high"][i],
                    "opened_at": iso(opened),
                    "last_reply_at": iso(last_reply) if last_reply else None,
                    "assignee": "csm.one@fixture.local"
                    if client != "cedar_family_clinic"
                    else "csm.two@fixture.local",
                }
            )
    health = [
        {
            "client": "northwind_ortho",
            "health_score": 72,
            "trend": "down",
            "as_of": iso(ANCHOR - timedelta(hours=2)),
        },
        {
            "client": "bluefield_imaging",
            "health_score": 88,
            "trend": "flat",
            "as_of": iso(ANCHOR - timedelta(hours=2)),
        },
        # stale on purpose: older than every rule's data_max_age
        {
            "client": "cedar_family_clinic",
            "health_score": 64,
            "trend": "down",
            "as_of": iso(ANCHOR - timedelta(days=3)),
        },
    ]
    return rows, health


def documents() -> list[dict]:
    base = "https://example.sharepoint.com/sites/client-context/Shared%20Documents"
    docs = []
    for client, info in CLIENTS.items():
        name = info["name"]
        docs += [
            {
                "client": client,
                "title": f"{name} - Statement of Work",
                "snippet": f"Scope for {name}: charge entry, payment posting, AR follow-up and denial management. Turnaround for charge entry is 48 hours.",
                "url": f"{base}/{client}/sow.docx",
                "modified": iso(ANCHOR - timedelta(days=40)),
            },
            {
                "client": client,
                "title": f"{name} - Escalation SOP",
                "snippet": f"Escalations for {name} go to the DM/AM first, then the hub leader after 4 hours.",
                "url": f"{base}/{client}/escalation-sop.docx",
                "modified": iso(ANCHOR - timedelta(days=12)),
            },
            {
                "client": client,
                "title": f"{name} - Payer list",
                "snippet": f"Top payers for {name}: Payer A, Payer B and Payer C. Timely filing limits differ by payer.",
                "url": f"{base}/{client}/payers.xlsx",
                "modified": iso(ANCHOR - timedelta(days=5)),
            },
        ]
    return docs


def users() -> list[dict]:
    rows = [
        ("hl.key@fixture.local", "Hub Leader Key", "Hub Leader", None),
        ("hl.small@fixture.local", "Hub Leader Small", "Hub Leader", None),
        ("dm.one@fixture.local", "DM One", "Delivery Manager", "hl.key@fixture.local"),
        ("dm.two@fixture.local", "DM Two", "Delivery Manager", "hl.key@fixture.local"),
        ("csm.one@fixture.local", "CSM One", "Client Success Manager", None),
        ("csm.two@fixture.local", "CSM Two", "Client Success Manager", None),
        ("ba.one@fixture.local", "BA One", "Business Analyst", None),
    ]
    return [
        {
            "id": f"00000000-0000-4000-8000-{i:012d}",
            "email": e,
            "name": n,
            "job_title": j,
            "manager": m,
        }
        for i, (e, n, j, m) in enumerate(rows, start=1)
    ]


def history(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """60 days of tasks with their life cycle, for backtests. Each task: created, due,
    completed_at (or null) and update times. Labels mark some alerts as wrong."""
    rows, labels, n = [], [], 0
    for d in range(60, 0, -1):
        day = ANCHOR - timedelta(days=d)
        for client, info in CLIENTS.items():
            for _ in range(rng.randint(2, 4)):
                n += 1
                created = day.replace(hour=4) + timedelta(minutes=rng.randint(0, 120))
                due = created + timedelta(hours=rng.randint(4, 10))
                late = rng.random() < 0.18
                done = (
                    due + timedelta(hours=rng.randint(1, 6))
                    if late
                    else due - timedelta(minutes=rng.randint(10, 180))
                )
                updates = sorted(
                    created
                    + timedelta(minutes=rng.randint(0, int((done - created).total_seconds() // 60)))
                    for _ in range(rng.randint(1, 4))
                )
                task_id = f"H-{n}"
                rows.append(
                    {
                        "task_id": task_id,
                        "client": client,
                        "title": rng.choice(TASK_TITLES),
                        "owner": info["dm_am"],
                        "created_at": iso(created),
                        "due": iso(due),
                        "completed_at": iso(done),
                        "updates": [iso(u) for u in updates],
                    }
                )
                if late and rng.random() < 0.15:
                    labels.append(
                        {
                            "rule_id": "R2",
                            "item_key": task_id,
                            "verdict": "wrong",
                            "note": "agreed extension",
                        }
                    )
    return rows, labels


def ticket_history(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """60 days of CS Hub tickets: opened, replies, closed. Labels mark some no-reply alerts as wrong."""
    rows, labels, n = [], [], 0
    subjects = [
        "Report question",
        "Call reschedule",
        "Denial trend",
        "Missing remits",
        "Portal access",
        "Slow charge entry",
    ]
    for d in range(60, 0, -1):
        day = ANCHOR - timedelta(days=d)
        for client in CLIENTS:
            if rng.random() < 0.5:
                continue
            n += 1
            opened = day.replace(hour=3) + timedelta(minutes=rng.randint(0, 600))
            slow = rng.random() < 0.2
            first_reply = opened + timedelta(
                hours=rng.randint(25, 40) if slow else rng.randint(1, 12)
            )
            replies = [first_reply + timedelta(hours=6 * i) for i in range(rng.randint(1, 3))]
            closed = replies[-1] + timedelta(hours=rng.randint(1, 24))
            ticket_id = f"HT-{n}"
            rows.append(
                {
                    "ticket_id": ticket_id,
                    "client": client,
                    "subject": rng.choice(subjects),
                    "priority": rng.choice(["low", "medium", "high"]),
                    "opened_at": iso(opened),
                    "replies": [iso(r) for r in replies],
                    "closed_at": iso(closed),
                    "assignee": "csm.two@fixture.local"
                    if client == "cedar_family_clinic"
                    else "csm.one@fixture.local",
                }
            )
            if slow and rng.random() < 0.2:
                labels.append(
                    {
                        "rule_id": "*",
                        "item_key": ticket_id,
                        "verdict": "wrong",
                        "note": "client asked to wait",
                    }
                )
    return rows, labels


def main() -> None:
    rng = random.Random(SEED)
    write("meta.json", {"anchor": iso(ANCHOR), "seed": SEED, "synthetic": True})
    write("smartsheet/tasks.json", tasks(rng))
    write("supaboard/metrics.json", metrics(rng))
    t, h = tickets(rng)
    write("cshub/tickets.json", t)
    write("cshub/health.json", h)
    write("sharepoint/documents.json", documents())
    write("entra/users.json", users())
    hist, labels = history(rng)
    write("history/tasks.json", hist)
    tickets_hist, ticket_labels = ticket_history(rng)
    write("history/labels.json", labels + ticket_labels)
    write("history/tickets.json", tickets_hist)


if __name__ == "__main__":
    main()
