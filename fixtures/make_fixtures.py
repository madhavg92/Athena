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


# skills to cover, notice periods and sign-off (the hub's people sheet)
TEAM_EXTRA = {
    "Analyst N1": {"also_trained": ["Denials"]},
    "Analyst N3": {"also_trained": ["AR follow-up", "Payment posting"]},
    "Analyst N4": {
        "signed_off": False,
        "sign_off_due": (ANCHOR + timedelta(days=9)).date().isoformat(),
    },
    "Analyst B1": {"also_trained": ["Prior auth"]},
    "Analyst B2": {"also_trained": ["Eligibility"]},
    "Analyst B3": {"on_notice_until": (ANCHOR + timedelta(days=25)).date().isoformat()},
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
                    **TEAM_EXTRA.get(name, {}),
                }
            )
            rows[-1].setdefault("also_trained", [])
            rows[-1].setdefault("signed_off", True)
            rows[-1].setdefault("sign_off_due", None)
            rows[-1].setdefault("on_notice_until", None)
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
            "summary": "Client escalated slow charge entry on the weekly call.",
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


# ---------------------------------------------------------------- money, economics, calendar (hub-leader agent)
APPEAL_WINDOW_DAYS = {PAYERS[0]: 60, PAYERS[1]: 30, PAYERS[2]: 90, PAYERS[3]: 45}
TF_LIMIT_DAYS = {PAYERS[0]: 180, PAYERS[1]: 120, PAYERS[2]: 90, PAYERS[3]: 180}
AVG_CLAIM_USD = {"northwind_ortho": 640, "bluefield_imaging": 410, "cedar_family_clinic": 185}


def denied_claims(denial_rows: list[dict], rng: random.Random) -> list[dict]:
    """Claim-level denials from the last 30 days, with amount, appeal deadline and work status."""
    since = (ANCHOR - timedelta(days=30)).date().isoformat()
    out, n = [], 0
    for r in denial_rows:
        if r["date"] < since:
            continue
        for _ in range(r["count"]):
            n += 1
            denied_on = datetime.fromisoformat(r["date"] + "T05:00:00+00:00")
            deadline = denied_on + timedelta(days=APPEAL_WINDOW_DAYS[r["payer"]])
            age = (ANCHOR - denied_on).days
            # the denials analyst is overloaded, so Northwind's Payer B prior-auth denials are mostly untouched
            backlog = r["client"] == "northwind_ortho" and r["reason_code"] == "CO-197"
            worked = rng.random() < (0.15 if backlog else min(0.9, 0.25 + age * 0.04))
            out.append(
                {
                    "claim_id": f"{r['client'][:2].upper()}-D{n:05d}",
                    "client": r["client"],
                    "payer": r["payer"],
                    "reason_code": r["reason_code"],
                    "reason": r["reason"],
                    "denied_on": r["date"],
                    "amount_usd": round(AVG_CLAIM_USD[r["client"]] * rng.uniform(0.6, 1.5)),
                    "appeal_deadline": deadline.date().isoformat(),
                    "status": "appealed" if worked else "not worked",
                }
            )
    return out


def ar_over_90_claims(aging: list[dict], rng: random.Random) -> list[dict]:
    """Claims in the over-90-day AR bucket (latest week), with their timely-filing deadline."""
    latest = {}
    for r in aging:
        if r["client"] not in latest or r["week_start"] > latest[r["client"]]["week_start"]:
            latest[r["client"]] = r
    out, n = [], 0
    for client, r in latest.items():
        left = r["over_90"]
        while left > 0:
            n += 1
            amount = min(left, round(AVG_CLAIM_USD[client] * rng.uniform(0.8, 2.5)))
            left -= amount
            payer = rng.choices(PAYERS, weights=[4, 2, 2, 2])[0]
            dos = ANCHOR - timedelta(
                days=rng.randint(91, TF_LIMIT_DAYS[payer] - 1 if TF_LIMIT_DAYS[payer] > 92 else 92)
            )
            tf = dos + timedelta(days=TF_LIMIT_DAYS[payer])
            out.append(
                {
                    "claim_id": f"{client[:2].upper()}-A{n:05d}",
                    "client": client,
                    "payer": payer,
                    "date_of_service": dos.date().isoformat(),
                    "amount_usd": amount,
                    "timely_filing_deadline": tf.date().isoformat(),
                    "last_touch": (ANCHOR - timedelta(days=rng.randint(3, 40))).date().isoformat(),
                }
            )
    return out


def client_economics() -> list[dict]:
    """Monthly revenue (Anka's fee), FTE and cost per client. Fee is a share of collections."""
    base = {
        "northwind_ortho": {"fee_pct": 5.0, "revenue": [14600, 14100, 13200], "fte": 3.5},
        "bluefield_imaging": {"fee_pct": 4.5, "revenue": [13300, 13600, 13900], "fte": 3.0},
        "cedar_family_clinic": {"fee_pct": 6.0, "revenue": [4600, 4400, 4100], "fte": 1.5},
    }
    cost_per_fte = 1400
    rows = []
    for client, b in base.items():
        for i, month in enumerate(["2026-07", "2026-08", "2026-09"]):
            rows.append(
                {
                    "client": client,
                    "month": month,
                    "revenue_usd": b["revenue"][i],
                    "fte": b["fte"],
                    "cost_usd": round(b["fte"] * cost_per_fte),
                    "fee_pct_of_collections": b["fee_pct"],
                    "query_id": "sb.economics.monthly",
                }
            )
    return rows


def calendar() -> list[dict]:
    """Meetings for the week (titles and times only; no content)."""

    def ist(d: int, h: int, m: int = 0) -> str:
        return iso(datetime(2026, 10, d, h, m, tzinfo=UTC) - timedelta(hours=5, minutes=30))

    return [
        {
            "owner": "hl.key@fixture.local",
            "start": ist(5, 15),
            "end": ist(5, 16),
            "title": "Weekly hub ops review",
            "type": "internal",
            "client": None,
            "attendees": ["hl.key@fixture.local", "dm.one@fixture.local", "dm.two@fixture.local"],
        },
        {
            "owner": "hl.key@fixture.local",
            "start": ist(6, 19),
            "end": ist(6, 19, 45),
            "title": "Northwind weekly call",
            "type": "client",
            "client": "northwind_ortho",
            "attendees": ["hl.key@fixture.local", "csm.one@fixture.local", "dm.one@fixture.local"],
        },
        {
            "owner": "hl.key@fixture.local",
            "start": ist(8, 18, 30),
            "end": ist(8, 19, 30),
            "title": "Bluefield quarterly review",
            "type": "client",
            "client": "bluefield_imaging",
            "attendees": ["hl.key@fixture.local", "csm.one@fixture.local", "dm.two@fixture.local"],
        },
    ]


# ---------------------------------------------------------------- hub operations (the hub leader's day)

HUB_DAY = ANCHOR.replace(hour=4, minute=30)  # 10:00 IST, start of the hub's day


def attendance() -> list[dict]:
    """Today's attendance from the roster sheet: who logged in, who is on leave, who is absent."""
    status = {
        "Analyst N2": "planned leave",
        "Analyst B2": "unplanned absence",
    }
    rows = []
    for client, members in TEAM.items():
        for i, (name, role, _fte, _leave) in enumerate(members):
            st = status.get(name, "present")
            rows.append(
                {
                    "date": ANCHOR.date().isoformat(),
                    "client": client,
                    "member": name,
                    "role": role,
                    "status": st,
                    "logged_in_at": iso(HUB_DAY + timedelta(minutes=4 + 7 * i))
                    if st == "present"
                    else None,
                }
            )
    return rows


# work type -> (items one FTE does in a day, daily inflow, turnaround target in work days, backlog 14 days ago)
WORK = {
    ("northwind_ortho", "Payment posting"): (120, 130, 2, 150),
    ("northwind_ortho", "AR follow-up"): (60, 55, 5, 160),
    ("northwind_ortho", "Denials"): (40, 44, 5, 80),
    ("northwind_ortho", "Charge entry"): (160, 76, 1, 30),
    ("bluefield_imaging", "Eligibility"): (90, 58, 1, 20),
    ("bluefield_imaging", "Prior auth"): (35, 33, 1, 12),
    ("bluefield_imaging", "Charge entry"): (140, 128, 1, 50),
    ("cedar_family_clinic", "Full cycle"): (80, 74, 3, 120),
    ("cedar_family_clinic", "AR follow-up"): (60, 28, 5, 70),
}


def workload(rng: random.Random) -> list[dict]:
    """Daily inflow, work done and backlog by client and work type (Supaboard). Today's row is
    the expected inflow and the backlog at the start of the day."""
    rows = []
    for (client, work_type), (norm, inflow, tat, backlog) in WORK.items():
        fte_by_role = {m[1]: m[2] for m in TEAM[client]}
        for back in range(13, -1, -1):
            day = (ANCHOR - timedelta(days=back)).date()
            if day.weekday() >= 5:
                continue
            fte = fte_by_role.get(work_type, 0.0)
            if work_type == "Payment posting" and back <= 3:
                fte = 0.0  # Analyst N2 on leave since Fri
            if work_type == "Prior auth" and back == 0:
                fte = 0.0  # Analyst B2 absent today
            surge = 1.2 if work_type == "Denials" and back <= 9 else 1.0  # Payer B portal change
            came = round(inflow * surge * rng.uniform(0.9, 1.1))
            if back == 0:
                done = 0
            else:
                done = min(backlog + came, round(norm * fte * rng.uniform(0.92, 1.05)))
                backlog = backlog + came - done
            daily = inflow * surge
            rows.append(
                {
                    "date": day.isoformat(),
                    "client": client,
                    "work_type": work_type,
                    "inflow": came,
                    "completed": done,
                    "backlog": backlog,
                    "oldest_days": max(1, -(-backlog // max(1, round(daily)))),
                    "tat_days": tat,
                    "per_fte_day": norm,
                    "query_id": f"sb.workload.{client}.{work_type.lower().replace(' ', '_')}",
                }
            )
    return rows


def blockers() -> list[dict]:
    """The hub's blocked-work log: logins, things waiting on the client, clearinghouse problems."""
    t = lambda days=0, hours=0: iso(HUB_DAY + timedelta(days=days, hours=hours))  # noqa: E731
    rows = [
        (
            "BL-301",
            "northwind_ortho",
            "access",
            "Practice system locked out Analyst N1 and Analyst N3; the MFA code goes to the client office manager, who starts at 18:30 IST",
            "client",
            2,
            0,
            0,
            t(0, 0.67),
            None,
            None,
            "open",
            None,
            "dm.one@fixture.local",
        ),
        (
            "BL-302",
            "bluefield_imaging",
            "access",
            "Payer C portal password for Analyst B1 expires; only the client admin can renew it",
            "client",
            0,
            0,
            0,
            t(-1, 2),
            t(1, 6),
            None,
            "open",
            None,
            "dm.two@fixture.local",
        ),
        (
            "BL-303",
            "northwind_ortho",
            "waiting_on_client",
            "Missing EOBs for 18 Payer A payments received since 28 Sep",
            "client",
            0,
            18,
            9450,
            t(-7, 1),
            None,
            None,
            "open",
            None,
            "dm.one@fixture.local",
        ),
        (
            "BL-304",
            "northwind_ortho",
            "waiting_on_client",
            "Fee schedule for the new Payer D contract not received; charges on hold",
            "client",
            0,
            34,
            12800,
            t(-12, 3),
            None,
            None,
            "open",
            None,
            "dm.one@fixture.local",
        ),
        (
            "BL-305",
            "bluefield_imaging",
            "waiting_on_client",
            "Referring physician NPI missing on 9 orders",
            "client",
            0,
            9,
            4100,
            t(-3, 2),
            None,
            None,
            "open",
            None,
            "dm.two@fixture.local",
        ),
        (
            "BL-306",
            "bluefield_imaging",
            "waiting_on_client",
            "Approval to write off 6 small balances",
            "client",
            0,
            6,
            380,
            t(-6, 5),
            None,
            None,
            "open",
            None,
            "dm.two@fixture.local",
        ),
        (
            "BL-307",
            "northwind_ortho",
            "clearinghouse",
            "Clearinghouse rejects Payer B claims after the payer ID change",
            "payer",
            0,
            27,
            15200,
            t(-2, 1),
            None,
            None,
            "open",
            None,
            "dm.one@fixture.local",
        ),
        (
            "BL-308",
            "northwind_ortho",
            "access",
            "User ID for the new joiner who starts Mon 12 Oct requested on 30 Sep; not created yet",
            "client",
            0,
            0,
            0,
            t(-5, 1),
            None,
            t(7, 0),
            "open",
            None,
            "dm.one@fixture.local",
        ),
        (
            "BL-309",
            "bluefield_imaging",
            "access",
            "VPN to the client imaging system down",
            "it",
            3,
            0,
            0,
            t(-1, 1),
            None,
            None,
            "closed",
            t(-1, 3.5),
            "dm.two@fixture.local",
        ),
        (
            "BL-310",
            "cedar_family_clinic",
            "waiting_on_client",
            "Credentialing letters for 2 new providers",
            "client",
            0,
            14,
            5200,
            t(-9, 2),
            None,
            None,
            "open",
            None,
            "dm.two@fixture.local",
        ),
    ]
    keys = [
        "blocker_id",
        "client",
        "kind",
        "summary",
        "waiting_on",
        "people_blocked",
        "items_held",
        "amount_usd",
        "opened_at",
        "expires_at",
        "due",
        "status",
        "closed_at",
        "owner",
    ]
    return [dict(zip(keys, r, strict=True)) for r in rows]


def quality() -> list[dict]:
    """Audit findings from the quality sheet: internal audits and errors the client found."""
    t = lambda days=0: iso(HUB_DAY + timedelta(days=days, hours=1))  # noqa: E731
    rows = [
        (
            "QF-41",
            "northwind_ortho",
            "client",
            "Payments posted to the wrong date of service on 5 accounts",
            "high",
            t(-5),
            t(-3),
            "open",
            None,
            "dm.one@fixture.local",
        ),
        (
            "QF-42",
            "northwind_ortho",
            "internal",
            "Adjustment codes used wrongly on 12 posts",
            "medium",
            t(-6),
            t(2),
            "open",
            None,
            "dm.one@fixture.local",
        ),
        (
            "QF-43",
            "bluefield_imaging",
            "internal",
            "Eligibility notes missing on 4 visits",
            "low",
            t(-2),
            t(5),
            "open",
            None,
            "dm.two@fixture.local",
        ),
        (
            "QF-44",
            "bluefield_imaging",
            "internal",
            "Wrong modifier on 3 charges",
            "medium",
            t(-8),
            t(-3),
            "closed",
            t(-1),
            "dm.two@fixture.local",
        ),
        (
            "QF-45",
            "cedar_family_clinic",
            "internal",
            "Follow-up notes not saved on 7 AR accounts",
            "medium",
            t(-4),
            t(3),
            "open",
            None,
            "dm.two@fixture.local",
        ),
    ]
    keys = [
        "finding_id",
        "client",
        "found_by",
        "summary",
        "severity",
        "opened_at",
        "due",
        "status",
        "closed_at",
        "owner",
    ]
    return [dict(zip(keys, r, strict=True)) for r in rows]


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
    money = random.Random(SEED + 200)  # separate stream again: earlier files stay unchanged
    write("supaboard/denied_claims.json", denied_claims(denial_rows, money))
    write(
        "supaboard/ar_over_90.json",
        ar_over_90_claims(json.loads((OUT / "supaboard/ar_aging.json").read_text()), money),
    )
    write("supaboard/economics.json", client_economics())
    write("graph/calendar.json", calendar())
    write("smartsheet/attendance.json", attendance())
    write("smartsheet/blockers.json", blockers())
    write("smartsheet/quality.json", quality())
    write("supaboard/workload.json", workload(random.Random(SEED + 300)))  # its own stream


if __name__ == "__main__":
    main()
