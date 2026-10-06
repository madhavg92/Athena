from sqlalchemy import select

from athena.core.db import Alert, as_utc
from athena.core.gateway import Source
from athena.tools.base import Tool, ToolContext, ToolResult, fmt_time


def get_my_alerts(ctx: ToolContext) -> ToolResult:
    scope = set(ctx.cfg.scope_of(ctx.actor))
    with ctx.gateway.db.session() as s:
        alerts = [
            a for a in s.scalars(select(Alert).where(Alert.state == "open")) if a.client in scope
        ]
    records = []
    for a in sorted(alerts, key=lambda a: (a.severity != "late", a.opened_at)):
        p = a.payload or {}
        records.append(
            {
                "alert_id": a.id,
                "rule": a.rule_id,
                "severity": a.severity,
                "client": ctx.cfg.owner_map.clients[a.client].name
                if a.client in ctx.cfg.owner_map.clients
                else a.client,
                "item": p.get("title")
                or p.get("subject")
                or p.get("metric")
                or a.item_key.split(":", 1)[-1],
                "item_key": a.item_key.split(":", 1)[-1],
                "opened": fmt_time(as_utc(a.opened_at), ctx.tz),
                "acknowledged": bool(p.get("_ack_by")),
                "snoozed_until": p.get("_snoozed_until"),
            }
        )
    return ToolResult(
        name="get_my_alerts",
        ok=True,
        records=records,
        sources=[Source(name="athena.alerts", as_of=ctx.now)] if records else [],
    )


TOOL = Tool(
    name="get_my_alerts",
    description="The open Athena alerts for the clients in the user's scope: alert id, rule, severity, client, item, when opened, and whether acknowledged or snoozed. Use for 'what needs my attention'.",
    parameters={"type": "object", "properties": {}},
    fn=get_my_alerts,
    needs_client=False,
)
