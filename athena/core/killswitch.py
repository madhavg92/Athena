"""Kill switches: global, per rule, per user. A switch that is on stops actions."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select

from athena.core.db import Database, KillSwitch, utcnow

Scope = Literal["global", "rule", "user"]


def set_switch(db: Database, scope: Scope, key: str, on: bool, set_by: str) -> None:
    key = "*" if scope == "global" else (key.lower() if scope == "user" else key)
    with db.session() as s:
        row = s.get(KillSwitch, (scope, key))
        if row is None:
            s.add(KillSwitch(scope=scope, key=key, on=on, set_by=set_by, set_at=utcnow()))
        else:
            row.on, row.set_by, row.set_at = on, set_by, utcnow()


def active_switches(db: Database) -> list[KillSwitch]:
    with db.session() as s:
        return list(s.scalars(select(KillSwitch).where(KillSwitch.on.is_(True))))


def blocked_by(db: Database, rule_id: str | None = None, users: list[str] = ()) -> str | None:
    """Return the reason if a kill switch blocks this action, else None."""
    wanted = {("global", "*")}
    if rule_id:
        wanted.add(("rule", rule_id))
    wanted |= {("user", u.lower()) for u in users if u}
    for row in active_switches(db):
        if (row.scope, row.key) in wanted:
            return (
                "kill switch: global"
                if row.scope == "global"
                else f"kill switch: {row.scope} {row.key}"
            )
    return None
