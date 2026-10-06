from athena.core import money
from athena.core.gateway import Source
from athena.tools.base import Tool, ToolContext, ToolResult


def get_client_economics(ctx: ToolContext, client: str | None = None) -> ToolResult:
    scope = ctx.cfg.scope_of(ctx.actor)
    clients = scope
    if client:
        from athena.tools.registry import resolve_client

        key = resolve_client(ctx, client)
        if key is None or key not in scope:
            return ToolResult(
                name="get_client_economics",
                ok=False,
                error=f"refused: {client} is not in your scope",
            )
        clients = [key]
    rows = money.economics(ctx.sources, clients)
    for r in rows:
        r["client"] = ctx.cfg.owner_map.clients[r["client"]].name
    return ToolResult(
        name="get_client_economics",
        ok=True,
        client=clients[0] if len(clients) == 1 else None,
        records=rows,
        sources=[Source(name="supaboard.economics", as_of=ctx.now)] if rows else [],
    )


TOOL = Tool(
    name="get_client_economics",
    description="Anka's monthly fee revenue, cost, FTE, revenue per FTE and margin per client (last 3 months). For hub leaders and above.",
    parameters={
        "type": "object",
        "properties": {"client": {"type": "string", "description": "Optional: one client."}},
    },
    fn=get_client_economics,
    needs_client=False,
)
