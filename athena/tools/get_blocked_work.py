from athena.core import standing
from athena.tools.base import Tool, ToolContext, ToolResult, scope_clients, sources_of

KINDS = ["access", "waiting_on_client", "clearinghouse", "payer_portal"]


def get_blocked_work(
    ctx: ToolContext, client: str | None = None, kind: str | None = None
) -> ToolResult:
    if kind and kind not in KINDS:
        return ToolResult(name="get_blocked_work", ok=False, error=f"kind must be one of {KINDS}")
    clients = scope_clients(ctx, "get_blocked_work", client)
    if isinstance(clients, ToolResult):
        return clients
    rows = [
        b
        for b in standing.blocked(ctx.cfg, ctx.sources, clients, ctx.now)
        if not kind or b["kind"] == kind
    ]
    for r in rows:
        r["due"] = r["due"].isoformat() if r["due"] else None
    return ToolResult(
        name="get_blocked_work",
        ok=True,
        client=clients[0] if len(clients) == 1 else None,
        records=rows,
        sources=sources_of(ctx.sources.read("smartsheet.blockers")) if rows else [],
    )


TOOL = Tool(
    name="get_blocked_work",
    description="Open blocked work from the hub's log: logins and access (people locked out, logins about to expire, new-joiner user IDs), things waiting on the client (items and dollars held, age in days), clearinghouse and payer problems. With hours lost and the owner. All clients in scope, or one; optionally one kind.",
    parameters={
        "type": "object",
        "properties": {
            "client": {"type": "string", "description": "Optional: one client."},
            "kind": {"type": "string", "enum": KINDS},
        },
    },
    fn=get_blocked_work,
    needs_client=False,
)
