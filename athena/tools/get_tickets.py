from athena.tools.base import (
    CLIENT_PARAM,
    Tool,
    ToolContext,
    ToolResult,
    is_stale,
    sources_of,
    to_model_rows,
)

FIELDS = ["ticket_id", "subject", "status", "priority", "opened_at", "last_reply_at", "assignee"]


def get_tickets(ctx: ToolContext, client: str, status: str | None = None) -> ToolResult:
    tickets = ctx.sources.read("cs_hub.tickets", client=client)
    tickets = [
        t for t in tickets if (t.get("status") == status if status else t.get("status") != "closed")
    ]
    health = ctx.sources.read("cs_hub.health", client=client)
    rows = to_model_rows(tickets, FIELDS, ctx.tz)
    if health:
        rows.insert(
            0, {"health_score": health[0].get("health_score"), "trend": health[0].get("trend")}
        )
    sources = sources_of(tickets + health)
    return ToolResult(
        name="get_tickets",
        ok=True,
        client=client,
        records=rows,
        sources=sources,
        stale=is_stale(ctx, sources),
    )


TOOL = Tool(
    name="get_tickets",
    description="CS Hub tickets for a client (open and pending unless a status is given) and the client health score.",
    parameters={
        "type": "object",
        "properties": {
            "client": CLIENT_PARAM,
            "status": {"type": "string", "enum": ["open", "pending", "closed"]},
        },
        "required": ["client"],
    },
    fn=get_tickets,
)
