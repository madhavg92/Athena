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


# ---------------------------------------------------------------- richer context (personal-agent questions)
# One story, so hard questions have real answers: Northwind's backlog and denial rate rise because an
# analyst is on leave and Payer B started denying prior auths (CO-197); the client was promised a
# recovery plan. Bluefield is steady; Cedar's AR is ageing.

PAYERS = [
    "Payer A (commercial)",
    "Payer B (Medicare Advantage)",
    "Payer C (Medicaid)",
    "Payer D (commercial)",
]
REASONS = {
    "CO-16": "missing or invalid claim information",
    "CO-197": "prior authorization absent",
    "CO-29": "timely filing limit passed",
    "CO-50": "not medically necessary",
    "CO-22": "covered by another payer (COB)",
}
TEAM = {
    "northwind_ortho": [
        ("Analyst N1", "AR follow-up", 1.0, False),
        ("Analyst N2", "Payment posting", 1.0, True),
        ("Analyst N3", "Denials", 1.0, False),
        ("Analyst N4", "Charge entry", 0.5, False),
    ],
    "bluefield_imaging": [
        ("Analyst B1", "Eligibility", 1.0, False),
        ("Analyst B2", "Prior auth", 1.0, False),
        ("Analyst B3", "Charge entry", 1.0, False),
    ],
    "cedar_family_clinic": [
        ("Analyst C1", "Full cycle", 1.0, False),
        ("Analyst C2", "AR follow-up", 0.5, False),
    ],
}


def claims(metric_rows: list[dict], rng: random.Random) -> tuple[list[dict], list[dict]]:
    """Daily claims (submitted, denied, paid) whose denial rate equals the denial_rate metric, and
    denials split by payer and reason (CARC code)."""
    rate = {
        (r["client"], r["date"]): r["actual"] for r in metric_rows if r["metric"] == "denial_rate"
    }
    volume = {"northwind_ortho": 220, "bluefield_imaging": 160, "cedar_family_clinic": 70}
    daily, denials = [], []
    for (client, day), pct in sorted(rate.items()):
        submitted = volume[client] + rng.randint(-15, 15)
        denied = round(submitted * pct / 100)
        daily.append(
            {
                "client": client,
                "date": day,
                "submitted": submitted,
                "denied": denied,
                "paid": submitted - denied - rng.randint(0, 5),
                "query_id": "sb.claims.daily",
            }
        )
        recent = day >= (ANCHOR - timedelta(days=21)).date().isoformat()
        for _ in range(denied):
            if client == "northwind_ortho" and recent and rng.random() < 0.45:
                payer, code = PAYERS[1], "CO-197"
            else:
                payer = rng.choices(PAYERS, weights=[4, 2, 2, 2])[0]
                code = rng.choices(list(REASONS), weights=[4, 2, 1, 2, 1])[0]
            denials.append((client, day, payer, code))
    grouped: dict[tuple, int] = {}
    for key in denials:
        grouped[key] = grouped.get(key, 0) + 1
    rows = [
        {
            "client": c,
            "date": d,
            "payer": p,
            "reason_code": code,
            "reason": REASONS[code],
            "count": n,
        }
        for (c, d, p, code), n in sorted(grouped.items())
    ]
    return daily, rows


def ar_aging(rng: random.Random) -> list[dict]:
    """Weekly AR aging snapshots (8 weeks), amounts in USD."""
    rows = []
    for client, base in (
        ("northwind_ortho", 1_200_000),
        ("bluefield_imaging", 900_000),
        ("cedar_family_clinic", 300_000),
    ):
        for w in range(8, 0, -1):
            week = (ANCHOR - timedelta(weeks=w)).date()
            week = week - timedelta(days=week.weekday())
            grow = (8 - w) / 8
            share90 = {
                "northwind_ortho": 0.12 + 0.07 * grow,
                "bluefield_imaging": 0.10,
                "cedar_family_clinic": 0.15 + 0.10 * grow,
            }[client]
            total = base * (1 + rng.uniform(-0.03, 0.03))
            b0, b31, b61 = total * 0.48, total * 0.22, total * (0.30 - share90)
            rows.append(
                {
                    "client": client,
                    "week_start": week.isoformat(),
                    "0_30": round(b0),
                    "31_60": round(b31),
                    "61_90": round(b61),
                    "over_90": round(total * share90),
                    "total": round(total),
                    "query_id": "sb.ar_aging.weekly",
                }
            )
    return rows


def task_history(tasks_rows: list[dict], rng: random.Random) -> list[dict]:
    """Changes to the current tasks: due dates moved, reassignments, status changes."""
    out = []
    for t in tasks_rows:
        due = datetime.fromisoformat(t["due"].replace("Z", "+00:00"))
        created = due - timedelta(days=rng.randint(2, 5))
        team = [m[0] for m in TEAM[t["client"]]]
        who = team[rng.randrange(len(team))]
        out.append(
            {
                "task_id": t["task_id"],
                "client": t["client"],
                "time": iso(created),
                "change": "created",
                "old": None,
                "new": f"assigned to {who}",
                "by": t["owner"],
            }
        )
        if (
            t["status"] != "Complete" and due < ANCHOR
        ):  # late tasks: due moved, and the analyst is away
            moved_from = due - timedelta(days=1)
            out.append(
                {
                    "task_id": t["task_id"],
                    "client": t["client"],
                    "time": iso(created + timedelta(hours=20)),
                    "change": "due date moved",
                    "old": iso(moved_from),
                    "new": iso(due),
                    "by": t["owner"],
                }
            )
            if t["client"] == "northwind_ortho":
                out.append(
                    {
                        "task_id": t["task_id"],
                        "client": t["client"],
                        "time": iso(due - timedelta(hours=30)),
                        "change": "assignee",
                        "old": "Analyst N1",
                        "new": "Analyst N2",
                        "by": t["owner"],
                    }
                )
        if t["status"] in ("In Progress", "Complete"):
            out.append(
                {
                    "task_id": t["task_id"],
                    "client": t["client"],
                    "time": t["last_update"],
                    "change": "status",
                    "old": "Not Started",
                    "new": t["status"],
                    "by": who,
                }
            )
    return out


def team() -> list[dict]:
    rows = []
    for client, members in TEAM.items():
        for name, role, fte, leave in members:
            rows.append(
                {
                    "client": client,
                    "member": name,
                    "role": role,
                    "fte": fte,
                    "on_leave_today": leave,
                    "leave_until": (ANCHOR + timedelta(days=4)).date().isoformat()
                    if leave
                    else None,
                    "open_items": 0
                    if leave
                    else {
                        "northwind_ortho": 140,
                        "bluefield_imaging": 95,
                        "cedar_family_clinic": 120,
                    }[client],
                    "utilisation_pct": 0
                    if leave
                    else {
                        "northwind_ortho": 118,
                        "bluefield_imaging": 92,
                        "cedar_family_clinic": 104,
                    }[client],
                }
            )
    return rows


def activity() -> list[dict]:
    d = lambda days, hour=6: iso(ANCHOR - timedelta(days=days) + timedelta(hours=hour - 6))  # noqa: E731
    return [
        {
            "client": "northwind_ortho",
            "time": d(21),
            "type": "meeting",
            "summary": "Monthly review. Client raised the rising backlog.",
            "owner": "csm.one@fixture.local",
        },
        {
            "client": "northwind_ortho",
            "time": d(12),
            "type": "escalation",
            "summary": "Client escalated slow charge entry (ticket CS-201 opened).",
            "owner": "csm.one@fixture.local",
        },
        {
            "client": "northwind_ortho",
            "time": d(6),
            "type": "commitment",
            "summary": "Anka promised a backlog recovery plan by 10 Oct.",
            "owner": "dm.one@fixture.local",
        },
        {
            "client": "northwind_ortho",
            "time": d(3),
            "type": "note",
            "summary": "Analyst N2 (payment posting) on leave until 09 Oct; no cover arranged yet.",
            "owner": "dm.one@fixture.local",
        },
        {
            "client": "northwind_ortho",
            "time": d(2),
            "type": "note",
            "summary": "Payer B started rejecting prior auths submitted through the old portal.",
            "owner": "dm.one@fixture.local",
        },
        {
            "client": "bluefield_imaging",
            "time": d(14),
            "type": "meeting",
            "summary": "Weekly call. Client happy; asked about quarter-end prior-auth volume.",
            "owner": "csm.one@fixture.local",
        },
        {
            "client": "bluefield_imaging",
            "time": d(4),
            "type": "commitment",
            "summary": "Anka to add one prior-auth analyst for quarter end from 13 Oct.",
            "owner": "dm.two@fixture.local",
        },
        {
            "client": "cedar_family_clinic",
            "time": d(18),
            "type": "meeting",
            "summary": "Monthly review. Health score falling; client unhappy with AR over 90 days.",
            "owner": "csm.two@fixture.local",
        },
        {
            "client": "cedar_family_clinic",
            "time": d(9),
            "type": "escalation",
            "summary": "Client asked for an AR clean-up plan.",
            "owner": "csm.two@fixture.local",
        },
    ]


def main() -> None:
    rng = random.Random(SEED)
    write("meta.json", {"anchor": iso(ANCHOR), "seed": SEED, "synthetic": True})
    task_rows = tasks(rng)
    metric_rows = metrics(rng)
    write("smartsheet/tasks.json", task_rows)
    write("supaboard/metrics.json", metric_rows)
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
    rich = random.Random(SEED + 100)  # separate stream: the files above stay unchanged
    daily, denial_rows = claims(metric_rows, rich)
    write("supaboard/claims.json", daily)
    write("supaboard/denials.json", denial_rows)
    write("supaboard/ar_aging.json", ar_aging(rich))
    write("smartsheet/task_history.json", task_history(task_rows, rich))
    write("smartsheet/team.json", team())
    write("cshub/activity.json", activity())


if __name__ == "__main__":
    main()
